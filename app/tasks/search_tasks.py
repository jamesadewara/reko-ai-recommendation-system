from loguru import logger
from app.core.broker import broker
from app.documents.user import UserDocument, VerifiedProfile
from app.services.deep_search import MultiSearchEngine, CONFIDENCE_THRESHOLD, _score_result
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# DEEP SEARCH TASK
# ─────────────────────────────────────────────────────────────────────────────

@broker.task(task_name="deep_search_user")
async def deep_search_user(user_id: str):
    """
    Background task: perform multi-provider deep search for a user,
    compile a corpus, and chain into analyze_user_data.
    """
    logger.info(f"[SearchTask] Starting deep search for user {user_id}")

    user = await UserDocument.find_by_id_or_uuid(user_id)
    if not user:
        logger.error(f"[SearchTask] User {user_id} not found")
        return

    search_service = MultiSearchEngine()

    try:
        search_results = await search_service.search_user(
            name=user.name or "Unknown",
            email=user.email,
        )

        corpus = search_service.compile_corpus(search_results)

        user.deep_search_results = search_results
        user.raw_corpus = corpus
        user.updated_at = datetime.utcnow()
        await user.save()

        logger.info(f"[SearchTask] Deep search complete for {user_id}. Corpus: {len(corpus)} chars")
        from app.tasks.analysis_tasks import analyze_user_data
        await analyze_user_data.kiq(user_id=user_id)

    except Exception as e:
        logger.error(f"[SearchTask] Deep search failed for {user_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULED: REFRESH & PRUNE SOCIAL PROFILES
# ─────────────────────────────────────────────────────────────────────────────

@broker.task(task_name="refresh_social_profiles")
async def refresh_social_profiles(user_id: str):
    """
    Scheduled refresh task — runs periodically (e.g. weekly) per user.

    Algorithm:
    1. Re-run MultiSearchEngine for every currently-verified profile URL.
    2. Re-score each result using the domain-aware confidence scorer.
    3. Update confidence_history on each VerifiedProfile.
    4. AUTO-REMOVE profiles whose current score dropped below CONFIDENCE_THRESHOLD
       (unless the user explicitly confirmed them — confirmed_by_user=True profiles
       are retained but flagged with a warning log).
    5. If any profile was added or removed → kick analyze_user_data to retrain
       the user's model from the updated corpus.
    """
    logger.info(f"[RefreshTask] Refreshing social profiles for user {user_id}")

    user = await UserDocument.find_by_id_or_uuid(user_id)
    if not user:
        logger.error(f"[RefreshTask] User {user_id} not found")
        return

    if not user.verified_profiles:
        logger.info(f"[RefreshTask] No verified profiles to refresh for {user_id}")
        return

    search_service = MultiSearchEngine()
    changed = False
    retained: list[VerifiedProfile] = []
    email_prefix = user.email.split("@")[0]

    for profile in user.verified_profiles:
        try:
            # Re-search using the known URL as the query
            result = await search_service.search(query=profile.url, max_results=5)
            results = result.get("results", [])

            # Find the best matching result for this URL (exact URL match preferred)
            best_result = next(
                (r for r in results if r.get("url") == profile.url),
                results[0] if results else None,
            )

            if best_result:
                new_conf = _score_result(best_result, profile.platform, user.name or "", email_prefix)
            else:
                # No result found → treat as zero confidence
                new_conf = 0.0

            # Append to history (keep last 10 readings)
            history = (profile.confidence_history or [])[-9:] + [new_conf]

            if new_conf < CONFIDENCE_THRESHOLD and not profile.confirmed_by_user:
                # Auto-remove: confidence dropped and user never explicitly confirmed
                logger.info(
                    f"[RefreshTask] Removing {profile.platform} profile '{profile.url}' "
                    f"for user {user_id} — confidence {new_conf:.2f} < threshold {CONFIDENCE_THRESHOLD}"
                )
                changed = True
                # Don't append to retained list — this is the removal
            else:
                if new_conf < CONFIDENCE_THRESHOLD and profile.confirmed_by_user:
                    logger.warning(
                        f"[RefreshTask] User-confirmed profile {profile.url} has low confidence "
                        f"({new_conf:.2f}) — keeping but flagging for review."
                    )
                retained.append(
                    VerifiedProfile(
                        platform=profile.platform,
                        url=profile.url,
                        title=profile.title,
                        confidence=new_conf,
                        confirmed_by_user=profile.confirmed_by_user,
                        added_at=profile.added_at,
                        last_verified_at=datetime.utcnow(),
                        confidence_history=history,
                    )
                )
                if abs(new_conf - profile.confidence) > 0.05:
                    changed = True  # Significant confidence shift

        except Exception as e:
            logger.error(f"[RefreshTask] Failed to refresh profile {profile.url}: {e}")
            # Keep the profile as-is on error (don't auto-remove)
            retained.append(profile)

    user.verified_profiles = retained
    user.last_profile_refresh = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    await user.save()

    removed_count = len(user.verified_profiles) - len(retained)
    logger.info(
        f"[RefreshTask] Done for {user_id}. "
        f"Retained: {len(retained)}, Removed: {removed_count}, Changed: {changed}"
    )

    # Re-train the user model if profiles changed
    if changed:
        logger.info(f"[RefreshTask] Profile change detected — triggering model retrain for {user_id}")
        try:
            await deep_search_user.kiq(user_id=user_id)
        except Exception as e:
            logger.error(f"[RefreshTask] Failed to kick retrain task: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# USER CREATION TASK
# ─────────────────────────────────────────────────────────────────────────────

@broker.task(task_name="create_user_profile")
async def create_user_profile(payload: dict):
    """
    Called by the auth service when a new user signs up.
    Payload: {auth_user_id, email, name, date_of_birth}
    """
    auth_user_id = payload.get("auth_user_id")
    email = payload.get("email")
    name = payload.get("name")
    dob_str = payload.get("date_of_birth")

    date_of_birth = None
    if dob_str:
        try:
            date_of_birth = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"[CreateProfile] Invalid date_of_birth format: {dob_str}")

    if not email:
        logger.error("[CreateProfile] Cannot create UserDocument: email missing")
        return

    existing_user = await UserDocument.find_one(UserDocument.email == email)
    if existing_user:
        logger.info(f"[CreateProfile] UserDocument already exists for {email}")
        existing_user.date_of_birth = date_of_birth
        await existing_user.save()
        user_id = str(existing_user.id)
    else:
        new_user = UserDocument(
            email=email,
            name=name,
            auth_user_id=auth_user_id,
            date_of_birth=date_of_birth,
        )
        await new_user.insert()
        user_id = str(new_user.id)
        logger.info(f"[CreateProfile] Created UserDocument for {email} (ID: {user_id})")

    await deep_search_user.kiq(user_id=user_id)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL: DAILY BATCH REFRESH
# ─────────────────────────────────────────────────────────────────────────────

@broker.task(task_name="global_daily_refresh")
async def global_daily_refresh():
    """
    Finds all active users and triggers a profile refresh for each.
    This is intended to be called by the scheduler using USER_REFRESH_CRON.
    """
    logger.info("[GlobalRefresh] Starting daily batch refresh for all users...")
    
    users = await UserDocument.find_all().to_list()
    count = 0
    for user in users:
        # Trigger refresh for each user
        await refresh_social_profiles.kiq(user_id=str(user.auth_user_id))
        count += 1
        
    logger.info(f"✅ [GlobalRefresh] Dispatched refresh tasks for {count} users.")
