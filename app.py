import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ================== CONFIG ==================
NUM_TABLES = 7
CHAIRS_PER_TABLE = 4
DB_NAME = "restaurant.db"

MENU_ITEMS = [
    "Porotta", "Dosa", "Idiyappam", "Chappathi",
    "Chicken Fry", "Chicken Curry", "Beef Fry", "Beef Curry",
    "Kurumma", "Kanthari Piece",
    "Set Bulsey", "Single Omblet", "Double Omblet",
    "Kanthari Combo", "49/- Combo", "Chicken fry Combo",
    "Beef Chapse Combo", "Pazhampori Combo",
    "Drink (20)", "Drink (40)"
]

# ================== PAGE ==================
st.set_page_config(page_title="Restaurant Order Manager", layout="wide")

# ================== AUTO REFRESH ==================
st_autorefresh(interval=2000)

# ================== DATABASE ==================
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    table_id INTEGER,
    chair_id INTEGER,
    item TEXT,
    qty INTEGER,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS chair_groups (
    table_id INTEGER,
    chair_id INTEGER,
    group_id INTEGER,
    PRIMARY KEY (table_id, chair_id)
)
""")

conn.commit()

# ================== FUNCTIONS ==================
def add_item(table_id, chair_id, item, qty):
    cur.execute(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
        (table_id, chair_id, item, qty, datetime.now())
    )
    conn.commit()

def clear_table(table_id):
    cur.execute("DELETE FROM orders WHERE table_id=?", (table_id,))
    conn.commit()

def get_orders(table_id, chair_id):
    cur.execute("""
        SELECT item, SUM(qty)
        FROM orders
        WHERE table_id=? AND chair_id=?
        GROUP BY item
    """, (table_id, chair_id))
    return dict(cur.fetchall())

def set_group(table_id, chair_id, group_id):
    cur.execute("""
        INSERT OR REPLACE INTO chair_groups VALUES (?, ?, ?)
    """, (table_id, chair_id, group_id))
    conn.commit()

def get_group(table_id, chair_id):
    cur.execute("""
        SELECT group_id FROM chair_groups
        WHERE table_id=? AND chair_id=?
    """, (table_id, chair_id))
    row = cur.fetchone()
    return row[0] if row else 1

# ================== SIDEBAR ==================
st.sidebar.title("🍽️ Table Selector")
selected_table = st.sidebar.radio(
    "Select Table",
    range(1, NUM_TABLES + 1),
    format_func=lambda x: f"Table {x}"
)

# ================== MAIN ==================
st.title(f"Table {selected_table}")
st.caption(f"Capacity: {CHAIRS_PER_TABLE} Chairs")

# ================== ADD ORDER ==================
st.subheader("📝 Add Order")
c1, c2, c3, c4 = st.columns([3, 1, 1, 1])

with c1:
    food = st.selectbox("Food Item", MENU_ITEMS)
with c2:
    qty = st.number_input("Qty", 1, 20, 1)
with c3:
    chair = st.selectbox("Chair", range(1, CHAIRS_PER_TABLE + 1))
with c4:
    st.write("")
    st.write("")
    if st.button("Add", type="primary"):
        add_item(selected_table, chair, food, qty)
        st.success("Order Added")

st.divider()

# ================== GROUPING ==================
with st.expander("🔗 Link Chairs / Split Bill"):
    cols = st.columns(CHAIRS_PER_TABLE)
    for i, col in enumerate(cols):
        chair_no = i + 1
        current_grp = get_group(selected_table, chair_no)
        with col:
            grp = st.selectbox(
                f"Chair {chair_no}",
                [1, 2, 3, 4],
                index=current_grp - 1,
                key=f"grp_{selected_table}_{chair_no}"
            )
            set_group(selected_table, chair_no, grp)

# ================== DISPLAY CHAIRS ==================
st.subheader("🪑 Current Orders")
chair_cols = st.columns(CHAIRS_PER_TABLE)

for i, col in enumerate(chair_cols):
    chair_no = i + 1
    orders = get_orders(selected_table, chair_no)
    grp_id = get_group(selected_table, chair_no)

    with col:
        st.info(f"Chair {chair_no} | Group {grp_id}")
        if orders:
            df = pd.DataFrame(orders.items(), columns=["Item", "Qty"])
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.markdown(f"**Items:** {sum(orders.values())}")
        else:
            st.caption("No orders")

# ================== BILL SUMMARY ==================
st.divider()
st.subheader("📊 Bill Summary")

groups = {}
for c in range(1, CHAIRS_PER_TABLE + 1):
    grp = get_group(selected_table, c)
    groups.setdefault(grp, []).append(c)

for grp_id, chairs in groups.items():
    summary = {}
    total = 0
    for c in chairs:
        orders = get_orders(selected_table, c)
        for item, qty in orders.items():
            summary[item] = summary.get(item, 0) + qty
            total += qty

    st.markdown(f"### 🧾 Group {grp_id} (Chairs {chairs})")
    if summary:
        df = pd.DataFrame(summary.items(), columns=["Item", "Qty"])
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.markdown(f"**Total Items:** {total}")
    else:
        st.caption("No orders")
    st.divider()

# ================== CLEAR ==================
if st.button("❌ Clear Table", type="secondary"):
    clear_table(selected_table)
    st.warning("Table cleared")
    st.rerun()

# ================== SIDEBAR STATUS ==================
st.sidebar.divider()
st.sidebar.markdown("### 📍 Restaurant Status")

cur.execute("""
SELECT COUNT(*) FROM (
    SELECT DISTINCT table_id, chair_id FROM orders
)
""")

active = cur.fetchone()[0] or 0
st.sidebar.write(f"Active Chairs: {active}/{NUM_TABLES * CHAIRS_PER_TABLE}")

