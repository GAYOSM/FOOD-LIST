import streamlit as st
import sqlite3
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from collections import defaultdict

# ================= CONFIG =================
NUM_TABLES = 7
DB_NAME = "restaurant.db"
MENU_ITEMS = ["",
    "Porotta", "Dosa", "Idly", "Chaya", "Lime",
    "Chicken Curry", "Beef Fry", "Vada", "Chappathi"
]

# ================= DB SETUP =================
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER,
    section_id INTEGER,
    item TEXT,
    qty INTEGER,
    status TEXT,
    created_at TEXT
)
""")
conn.commit()

# ================= FUNCTIONS =================
def add_order(table_id, section_id, item, qty=1):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO orders (table_id, section_id, item, qty, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (table_id, section_id, item, qty, "Preparing", timestamp)
    )
    conn.commit()

def get_orders(table_id=None, section_id=None, status=None):
    query = "SELECT * FROM orders WHERE 1=1"
    params = []
    if table_id:
        query += " AND table_id=?"
        params.append(table_id)
    if section_id:
        query += " AND section_id=?"
        params.append(section_id)
    if status:
        if isinstance(status, list):
            if status:
                placeholders = ",".join("?" for _ in status)
                query += f" AND status IN ({placeholders})"
                params.extend(status)
            else:
                # if list is empty, return no results
                query += " AND 1=0"
        else:
            query += " AND status=?"
            params.append(status)
    query += " ORDER BY created_at DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()

def get_new_section_id(table_id):
    cur.execute("SELECT MAX(section_id) FROM orders WHERE table_id=?", (table_id,))
    max_id = cur.fetchone()[0]
    return (max_id or 0) + 1

def update_qty(order_id, change):
    cur.execute("SELECT qty FROM orders WHERE id=?", (order_id,))
    row = cur.fetchone()
    if row:
        qty = row[0] + change
        if qty <= 0:
            cur.execute("DELETE FROM orders WHERE id=?", (order_id,))
        else:
            cur.execute("UPDATE orders SET qty=? WHERE id=?", (qty, order_id))
        conn.commit()
        st.rerun()

def update_status(order_id, status):
    cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    st.rerun()

def delete_order(order_id):
    cur.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit()
    st.rerun()


# ================= SESSION STATE =================
if "selected_table" not in st.session_state:
    st.session_state.selected_table = 1

# ================= UI =================
st.set_page_config(page_title="Restaurant Order Manager", layout="wide", initial_sidebar_state="collapsed")
st.title("🍽️ Restaurant Order Manager")

# View switcher
view = st.sidebar.radio("Switch View", ["Waiter", "Kitchen"], 0)

# ================= WAITER VIEW =================
if view == "Waiter":
    st.sidebar.header("Waiter Controls")
    
    # --- Table Selection in Sidebar ---
    st.sidebar.subheader("Select Table")
    st.session_state.selected_table = st.sidebar.number_input("Table", min_value=1, max_value=NUM_TABLES, value=st.session_state.selected_table)

    st.header(f"Table {st.session_state.selected_table}")

    # --- Get all orders for the table and group by section ---
    table_orders = get_orders(table_id=st.session_state.selected_table)
    sections = defaultdict(list)
    for order in table_orders:
        sections[order[2]].append(order) # order[2] is section_id

    # --- Menu and Ordering ---
    with st.expander("Add New Item", expanded=True):
        col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
        with col1:
            selected_item = st.selectbox("Select an item", MENU_ITEMS)
        with col2:
            quantity = st.number_input("Quantity", min_value=1, value=1)
        with col3:
            existing_sections = sorted(sections.keys())
            section_options = [f"Section {s}" for s in existing_sections] + ["Create New Section"]
            selected_section_str = st.selectbox("Choose Section", options=section_options)
        
        with col4:
            st.write("") # align button
            st.write("") # align button
            if st.button("Add to Order", use_container_width=True, type="primary"):
                if selected_section_str == "Create New Section":
                    target_section = get_new_section_id(st.session_state.selected_table)
                else:
                    target_section = int(selected_section_str.split(" ")[1])
                
                add_order(st.session_state.selected_table, target_section, selected_item, quantity)
                st.success(f"Added {quantity} x {selected_item} to Table {st.session_state.selected_table}, {selected_section_str}")
                st.rerun()

    st.subheader("Current Orders")
    if not sections:
        st.info("No orders for this table yet.")
    else:
        for section_id, orders in sorted(sections.items()):
            with st.container(border=True):
                st.markdown(f"**Section {section_id}**")
                for o in orders:
                    order_id, _, _, item, qty, status, _ = o
                    
                    c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 2, 1])
                    c1.markdown(f"**{item}**")
                    c2.markdown(f"`{qty}`")

                    with c3:
                        cc1, cc2 = st.columns(2)
                        if cc1.button("➖", key=f"dec_{order_id}", use_container_width=True):
                            update_qty(order_id, -1)
                        if cc2.button("➕", key=f"inc_{order_id}", use_container_width=True):
                            update_qty(order_id, 1)

                    if status == "Preparing":
                        c4.info("Preparing")
                    elif status == "Ready":
                        c4.button("Mark as Served", key=f"serve_{order_id}", on_click=update_status, args=(order_id, "Served"), use_container_width=True, type="primary")
                    else: # Served
                        c4.success("Served")
                    
                    c5.button("🗑️", key=f"del_{order_id}", on_click=delete_order, args=(order_id,), use_container_width=True)


# ================= KITCHEN VIEW =================
elif view == "Kitchen":
    st.header("🍳 Kitchen View")
    
    # --- Auto-refresh control ---
    if st.sidebar.checkbox("Auto-refresh", value=True):
        st_autorefresh(interval=5000, key="kitchen_refresh")

    # --- Order Filtering ---
    st.sidebar.header("Kitchen Filters")
    filter_status = st.sidebar.multiselect("Filter by Status", ["Preparing", "Ready", "Served"], default=["Preparing", "Ready"])
    
    # --- Display Orders in Columns ---
    all_orders = get_orders(status=filter_status)
    if not all_orders:
        st.warning("No orders with selected filters.")
    else:
        num_columns = 3
        cols = st.columns(num_columns)
        for i, o in enumerate(all_orders):
            order_id, table_id, section_id, item, qty, status, created_at = o
            with cols[i % num_columns].container(border=True):
                st.markdown(f"**Table {table_id} | Section {section_id}**")
                st.markdown(f"### {qty} x {item}")
                st.caption(f"Ordered at: {created_at}")
                
                if status == "Preparing":
                    st.info("Status: Preparing...")
                    if st.button("Mark as Ready", key=f"kitchen_ready_{order_id}", use_container_width=True, type="primary"):
                        update_status(order_id, "Ready")
                elif status == "Ready":
                    st.warning("Status: Ready")
                else: # Served
                    st.success("Status: Served")