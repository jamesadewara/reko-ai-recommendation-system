import asyncio
import os
import sys
import typer
from typing import List

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import init_db
from app.core.config import settings
from app.documents.item import ItemDocument, ItemMetadata
from app.services.embedding_encoder import encode_text
from loguru import logger

app = typer.Typer()

ITEMS = [
    # MOVIES
    {
        "name": "King of Boys", 
        "category": "movies", 
        "description": "A Nigerian political thriller following Eniola Salami, a businesswoman and philanthropist with a secret past.", 
        "metadata": {"duration_minutes": 169, "genre": ["Thriller"], "location_tags": ["Lagos"], "nigerian_context": True, "image_url": "https://image.tmdb.org/t/p/w500/king_of_boys.jpg"}, 
        "popularity_score": 0.9
    },
    {
        "name": "The Wedding Party", 
        "category": "movies", 
        "description": "A romantic comedy about a lavish Nigerian wedding in Lagos that doesn't go as planned.", 
        "metadata": {"duration_minutes": 110, "genre": ["Romance"], "location_tags": ["Lagos", "Victoria Island"], "nigerian_context": True}, 
        "popularity_score": 0.85
    },
    {
        "name": "Citation", 
        "category": "movies", 
        "description": "A Nigerian drama about a bright student who speaks out against sexual harassment by a professor.", 
        "metadata": {"duration_minutes": 131, "genre": ["Drama"], "location_tags": ["Lagos"], "nigerian_context": True}, 
        "popularity_score": 0.8
    },
    {
        "name": "Living in Bondage: Breaking Free", 
        "category": "movies", 
        "description": "A modern sequel to the classic Nollywood film, exploring the occult and wealth in Lagos.", 
        "metadata": {"duration_minutes": 148, "genre": ["Thriller"], "location_tags": ["Lagos"], "nigerian_context": True}, 
        "popularity_score": 0.82
    },
    {
        "name": "Interstellar", 
        "category": "movies", 
        "description": "A team of explorers travel through a wormhole in space to ensure humanity's survival.", 
        "metadata": {"duration_minutes": 169, "genre": ["Sci-Fi"], "nigerian_context": False}, 
        "popularity_score": 0.95
    },
    {
        "name": "Arrival", 
        "category": "movies", 
        "description": "A linguist works with the military to communicate with alien lifeforms after twelve mysterious spacecraft appear around the world.", 
        "metadata": {"duration_minutes": 116, "genre": ["Sci-Fi"], "nigerian_context": False}, 
        "popularity_score": 0.92
    },
    # FOOD
    {
        "name": "Party Jollof Rice at The Place", 
        "category": "food", 
        "description": "Spicy smoky Nigerian party jollof rice served with fried plantains and coleslaw. A Lagos favorite.", 
        "metadata": {"location_tags": ["Lekki", "Ikeja"], "nigerian_context": True}, 
        "popularity_score": 0.95
    },
    {
        "name": "Suya from Ikeja Street Vendor", 
        "category": "food", 
        "description": "Grilled spicy beef skewers with peanut spice blend, onions, and tomatoes. Authentic Northern Nigerian street food.", 
        "metadata": {"location_tags": ["Ikeja", "Abuja"], "nigerian_context": True}, 
        "popularity_score": 0.9
    },
    {
        "name": "Amala & Ewedu with Gbegiri", 
        "category": "food", 
        "description": "Yam flour swallow served with jute leaf soup and bean soup. A staple in Yoruba cuisine.", 
        "metadata": {"location_tags": ["Ibadan", "Lagos"], "nigerian_context": True}, 
        "popularity_score": 0.88
    },
    {
        "name": "Egusi Soup with Pounded Yam", 
        "category": "food", 
        "description": "Melon seed soup with vegetables and assorted meat, served with smooth pounded yam.", 
        "metadata": {"location_tags": ["Lagos", "Abuja"], "nigerian_context": True}, 
        "popularity_score": 0.92
    },
    # MUSIC
    {
        "name": "Made in Lagos by Wizkid", 
        "category": "music", 
        "description": "Wizkid's fourth studio album blending Afrobeats, reggae, and R&B. Features Essence and Ginger.", 
        "metadata": {"genre": ["Afrobeats"], "nigerian_context": True}, 
        "popularity_score": 0.95
    },
    {
        "name": "Twice as Tall by Burna Boy", 
        "category": "music", 
        "description": "Burna Boy's Grammy-winning album fusing Afrobeats with dancehall and hip-hop.", 
        "metadata": {"genre": ["Afrobeats"], "nigerian_context": True}, 
        "popularity_score": 0.94
    },
    {
        "name": "Born in the Wild by Tems", 
        "category": "music", 
        "description": "Tems' debut album exploring R&B and Afrobeats with raw emotional depth.", 
        "metadata": {"genre": ["R&B/Afrobeats"], "nigerian_context": True}, 
        "popularity_score": 0.9
    },
    # BOOKS
    {
        "name": "Americanah by Chimamanda Ngozi Adichie", 
        "category": "books", 
        "description": "A novel about a young Nigerian woman who emigrates to America and her experiences with race and identity.", 
        "metadata": {"nigerian_context": True}, 
        "popularity_score": 0.93
    },
    {
        "name": "Things Fall Apart by Chinua Achebe", 
        "category": "books", 
        "description": "The classic novel about pre-colonial life in southeastern Nigeria and the arrival of Europeans.", 
        "metadata": {"nigerian_context": True}, 
        "popularity_score": 0.95
    },
    {
        "name": "Purple Hibiscus by Chimamanda Ngozi Adichie", 
        "category": "books", 
        "description": "A coming-of-age story set in postcolonial Nigeria about family, faith, and freedom.", 
        "metadata": {"nigerian_context": True}, 
        "popularity_score": 0.88
    }
]

async def seed_data():
    logger.info("🔗 Connecting to database...")
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    
    logger.info(f"🌱 Seeding {len(ITEMS)} items...")
    
    for item_data in ITEMS:
        # Check if item already exists
        existing = await ItemDocument.find_one(ItemDocument.name == item_data["name"])
        if existing:
            logger.info(f"⏩ Item '{item_data['name']}' already exists, skipping.")
            continue
            
        # Compute embedding
        logger.info(f"🧠 Computing embedding for '{item_data['name']}'...")
        embedding = encode_text(f"{item_data['name']} {item_data['description']}")
        
        # Create Document
        item = ItemDocument(
            name=item_data["name"],
            category=item_data["category"],
            description=item_data["description"],
            embedding=embedding,
            metadata=ItemMetadata(**item_data["metadata"]),
            popularity_score=item_data["popularity_score"]
        )
        await item.insert()
        logger.info(f"✅ Saved '{item_data['name']}'")

    logger.info("✨ Seeding complete!")

@app.command()
def seed(confirm: bool = typer.Option(False, "--confirm", help="Confirm you want to seed the database")):
    if not confirm:
        print("❌ Please use --confirm to proceed with seeding.")
        raise typer.Abort()
    
    asyncio.run(seed_data())

if __name__ == "__main__":
    app()
