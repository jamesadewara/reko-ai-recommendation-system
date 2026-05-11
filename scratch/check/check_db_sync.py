from pymongo import MongoClient

def main():
    client = MongoClient("mongodb://localhost:27017")
    db = client.reko_ai_system_db
    print(f"Reviews: {db.reviews.count_documents({})}")
    print(f"Users: {db.users.count_documents({})}")
    print(f"Items: {db.items.count_documents({})}")
    client.close()

if __name__ == "__main__":
    main()
