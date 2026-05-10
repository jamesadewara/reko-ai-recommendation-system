from loguru import logger
from app.core.broker import broker
from app.documents.user import UserDocument
from app.services.deep_search import MultiSearchEngine
from datetime import datetime

@broker.task(task_name="deep_search_user")
async def deep_search_user(user_id: str):
    """
    Background task to perform deep search for a user and trigger analysis.
    """
    logger.info(f"[Tasks] Starting deep search for user {user_id}")
    
    user = await UserDocument.get(user_id)
    if not user:
        logger.error(f"[Tasks] User {user_id} not found for deep search")
        return

    search_service = MultiSearchEngine()
    
    try:
        # Perform search
        search_results = await search_service.search_user(
            name=user.name or "Unknown",
            email=user.email
        )
        
        # Compile corpus
        corpus = search_service.compile_corpus(search_results)
        
        # Update Document
        user.deep_search_results = search_results
        user.raw_corpus = corpus
        await user.save()
        
        logger.info(f"[Tasks] Deep search complete for {user_id}. Corpus length: {len(corpus)}")
        
        # Emit next task: analyze_user_data
        await broker.kick("analyze_user_data", user_id=user_id)
        
    except Exception as e:
        logger.error(f"[Tasks] Deep search failed for user {user_id}: {e}")

@broker.task(task_name="create_user_profile")
async def create_user_profile(payload: dict):
    """
    Called by auth service when a new user signs up.
    Payload: {auth_user_id, email, name}
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
            logger.warning(f"[Tasks] Invalid date_of_birth format: {dob_str}")

    if not email:
        logger.error("[Tasks] Cannot create UserDocument: email missing in payload")
        return

    # Check if user already exists
    existing_user = await UserDocument.find_one(UserDocument.email == email)
    if existing_user:
        logger.info(f"[Tasks] UserDocument already exists for email {email}")
        existing_user.date_of_birth = date_of_birth
        await existing_user.save()
        user_id = str(existing_user.id)
    else:
        # Create new UserDocument
        new_user = UserDocument(
            email=email,
            name=name,
            auth_user_id=auth_user_id,
            date_of_birth=date_of_birth
        )
        await new_user.insert()
        user_id = str(new_user.id)
        logger.info(f"[Tasks] Created new UserDocument for email {email} (ID: {user_id})")

    # Trigger deep search
    await broker.kick("deep_search_user", user_id=user_id)

@broker.task(task_name="send_otp_email")
async def send_otp_email_stub(*args, **kwargs):
    """
    Stub to prevent 'task not found' warnings if auth tasks 
    accidentally end up in the recommendation queue.
    """
    logger.warning("[Recommendation] Received 'send_otp_email' task. This belongs to the Auth system. Ignoring.")
    return

@broker.task(task_name="send_password_reset_email")
async def send_password_reset_email_stub(*args, **kwargs):
    """
    Stub for password reset emails.
    """
    logger.warning("[Recommendation] Received 'send_password_reset_email' task. Ignoring.")
    return
