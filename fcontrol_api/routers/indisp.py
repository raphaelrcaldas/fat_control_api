    if db_indisp is None or db_indisp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Indisp not found or is deleted")

    # Existing update logic
    # ...
