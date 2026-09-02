person_id = args.get("person_id", "bob")
ids = []
for box in search_around("Person", person_id, "packages"):
    if box["properties"].get("status") != "delivered":
        ids.append(box["id"])
result = ids
