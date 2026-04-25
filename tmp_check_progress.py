from goofish_insight.infrastructure.database import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM items")).scalar()

    rows = conn.execute(text("""
        SELECT review_status, COUNT(*) as cnt
        FROM items
        GROUP BY review_status
        ORDER BY cnt DESC
    """)).fetchall()

    try:
        sp_rows = conn.execute(text("""
            SELECT second_pass_status, COUNT(*) as cnt
            FROM items
            GROUP BY second_pass_status
            ORDER BY cnt DESC
        """)).fetchall()
        print("=== Second Pass Status ===")
        for r in sp_rows:
            print(f"  {r[0]}: {r[1]}")
    except Exception as e:
        print(f"second_pass_status column not found: {e}")

    print()
    print("=== Review Status ===")
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
    print(f"  TOTAL: {total}")

    rej = conn.execute(text("SELECT COUNT(*) FROM item_ingest_rejection")).scalar()
    print(f"  Ingest rejections: {rej}")

    try:
        spec = conn.execute(text("SELECT COUNT(*) FROM item_spec_enrichments")).scalar()
        print(f"  Spec enrichments: {spec}")
    except Exception:
        pass

    try:
        cat_rows = conn.execute(text("""
            SELECT c.name, COUNT(*) as cnt
            FROM items i
            JOIN categories c ON i.category_id = c.id
            GROUP BY c.name
            ORDER BY cnt DESC
        """)).fetchall()
        print()
        print("=== By Category ===")
        for r in cat_rows:
            print(f"  {r[0]}: {r[1]}")
    except Exception as e:
        print(f"Category join failed: {e}")

    try:
        pending_review = conn.execute(text("""
            SELECT COUNT(*) FROM items
            WHERE review_status = 'pending_audit'
        """)).scalar()
        print(f"\n  Pending audit: {pending_review}")
    except Exception:
        pass

    try:
        complete = conn.execute(text("""
            SELECT COUNT(*) FROM items
            WHERE review_status = 'complete'
        """)).scalar()
        print(f"  Complete: {complete}")
    except Exception:
        pass

    try:
        garbage = conn.execute(text("""
            SELECT COUNT(*) FROM items
            WHERE review_status = 'garbage'
        """)).scalar()
        print(f"  Garbage: {garbage}")
    except Exception:
        pass

    try:
        low_conf = conn.execute(text("""
            SELECT COUNT(*) FROM items
            WHERE second_pass_status = 'low_confidence'
        """)).scalar()
        print(f"  Low confidence (2nd pass): {low_conf}")
    except Exception:
        pass

    try:
        rescued = conn.execute(text("""
            SELECT COUNT(*) FROM items
            WHERE second_pass_status = 'rescued'
        """)).scalar()
        print(f"  Rescued (2nd pass): {rescued}")
    except Exception:
        pass

    try:
        unresolved = conn.execute(text("""
            SELECT COUNT(*) FROM items
            WHERE second_pass_status = 'unresolved'
        """)).scalar()
        print(f"  Unresolved (2nd pass): {unresolved}")
    except Exception:
        pass
