import streamlit as st
import sqlite3
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from collections import defaultdict

# ================= CONFIG =================
NUM_TABLES = 7
DB_NAME = "restaurant.db"


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
    created_at TEXT,
    price REAL,
    is_parcel INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS menu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    price REAL NOT NULL
)
""")

# Backwards compatibility for old databases - add missing columns
cur.execute("PRAGMA table_info(orders)")
columns = [row[1] for row in cur.fetchall()]
if "price" not in columns:
    cur.execute("ALTER TABLE orders ADD COLUMN price REAL DEFAULT 0")
if "section_id" not in columns:
    cur.execute("ALTER TABLE orders ADD COLUMN section_id INTEGER DEFAULT 1")
if "is_parcel" not in columns:
    cur.execute("ALTER TABLE orders ADD COLUMN is_parcel INTEGER DEFAULT 0")


# One-time migration from hardcoded values to the database
cur.execute("SELECT COUNT(*) FROM menu")
if cur.fetchone()[0] == 0:
    MIGRATION_MENU_ITEMS = [
        "Porotta", "Dosa", "Idly", "Chaya", "Lime",
        "Chicken Curry", "Beef Fry", "Vada", "Chappathi"
    ]
    MIGRATION_MENU_PRICES = {
        "Porotta": 12, "Dosa": 40, "Idly": 30, "Chaya": 10, "Lime": 20,
        "Chicken Curry": 150, "Beef Fry": 180, "Vada": 10, "Chappathi": 15
    }
    for item in MIGRATION_MENU_ITEMS:
        if item: # Skip empty string
            price = MIGRATION_MENU_PRICES.get(item, 0)
            # Using INSERT OR IGNORE to be safe
            cur.execute("INSERT OR IGNORE INTO menu (name, price) VALUES (?, ?)", (item, price))
conn.commit()


# ================= FUNCTIONS =================
def add_order(table_id, section_id, item, qty=1, is_parcel=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Get price from menu table
    cur.execute("SELECT price FROM menu WHERE name=?", (item,))
    result = cur.fetchone()
    price = result[0] if result else 0
    is_parcel_int = 1 if is_parcel else 0

    cur.execute(
        "INSERT INTO orders (table_id, section_id, item, qty, status, created_at, price, is_parcel) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (table_id, section_id, item, qty, "Preparing", timestamp, price, is_parcel_int)
    )
    conn.commit()

def get_orders(table_id=None, section_id=None, status=None, items=None):
    query = "SELECT id, table_id, section_id, item, qty, status, created_at, price, is_parcel FROM orders WHERE 1=1"
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
    
    if items: # if items is not None and not an empty list
        placeholders = ",".join("?" for _ in items)
        query += f" AND item IN ({placeholders})"
        params.extend(items)

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

def delete_section(table_id, section_id):
    cur.execute("DELETE FROM orders WHERE table_id=? AND section_id=?", (table_id, section_id))
    conn.commit()
    st.rerun()

def toggle_parcel_status(order_id):
    cur.execute("UPDATE orders SET is_parcel = NOT is_parcel WHERE id=?", (order_id,))
    conn.commit()
    st.rerun()

# --- Menu CRUD ---
def get_menu_items():
    cur.execute("SELECT id, name, price FROM menu ORDER BY name")
    return cur.fetchall()

def add_menu_item(name, price):
    try:
        cur.execute("INSERT INTO menu (name, price) VALUES (?, ?)", (name, price))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error(f"Error: Item '{name}' already exists in the menu.")
        return False

def update_menu_item(item_id, name, price):
    try:
        cur.execute("UPDATE menu SET name=?, price=? WHERE id=?", (name, price, item_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error(f"Error: An item with name '{name}' may already exist.")
        return False

def delete_menu_item(item_id):
    cur.execute("DELETE FROM menu WHERE id=?", (item_id,))
    conn.commit()

def set_table(table_number):
    st.session_state.selected_table = table_number



# ================= SESSION STATE =================
if "selected_table" not in st.session_state:
    st.session_state.selected_table = 1

# ================= UI =================
st.set_page_config(page_title="Restaurant Order Manager", layout="wide", initial_sidebar_state="collapsed")
st.title("🍽️ Restaurant Order Manager")

# View switcher
view = st.sidebar.radio("Switch View", ["Waiter", "Kitchen", "Configuration"], 0)

# ================= WAITER VIEW =================
if view == "Waiter":
    st.sidebar.header("Waiter Controls")

    # --- Table Selection ---
    st.subheader("Select a Table")
    cols = st.columns(NUM_TABLES)
    for i in range(NUM_TABLES):
        table_num = i + 1
        with cols[i]:
            is_selected = (st.session_state.selected_table == table_num)
            st.button(
                f"Table {table_num}",
                key=f"table_{table_num}",
                on_click=set_table,
                args=(table_num,),
                type="primary" if is_selected else "secondary",
                use_container_width=True
            )
    
    st.markdown("---")
    st.header(f"Table {st.session_state.selected_table}")


    # --- Get all orders for the table and group by section ---
    table_orders = get_orders(table_id=st.session_state.selected_table)
    sections = defaultdict(list)
    for order in table_orders:
        sections[order[2]].append(order) # order[2] is section_id

    # --- Create a price lookup dictionary ---
    menu_prices_dict = {name: price for _, name, price in get_menu_items()}

    # --- Menu and Ordering ---
    with st.expander("Add New Item", expanded=True):
        col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
        with col1:
            menu_item_names = [""] + sorted(list(menu_prices_dict.keys()))
            selected_item = st.selectbox("Select an item", menu_item_names)
        with col2:
            quantity = st.number_input("Quantity", min_value=1, value=1)
            is_parcel_add = st.checkbox("Parcel", key="add_parcel")
        with col3:
            existing_sections = sorted(sections.keys())
            section_options = [f"Section {s}" for s in existing_sections] + ["Create New Section"]
            selected_section_str = st.selectbox("Choose Section", options=section_options)

        with col4:
            st.write("") # align button
            st.write("") # align button
            if st.button("Add to Order", use_container_width=True, type="primary"):
                if selected_item == "":
                    st.warning("Please select an item.")
                else:
                    if selected_section_str == "Create New Section":
                        target_section = get_new_section_id(st.session_state.selected_table)
                    else:
                        target_section = int(selected_section_str.split(" ")[1])

                    add_order(st.session_state.selected_table, target_section, selected_item, quantity, is_parcel=is_parcel_add)
                    st.success(f"Added {quantity} x {selected_item} to Table {st.session_state.selected_table}, {selected_section_str}")
                    st.rerun()

    st.subheader("Current Orders")
    if not sections:
        st.info("No orders for this table yet.")
    else:
        grand_total = 0
        
        # Header
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([3, 1, 1, 1, 1, 2, 2, 1])
        c1.markdown("**Item**")
        c2.markdown("**Qty**")
        c3.markdown("**Price**")
        c4.markdown("**Total**")
        c5.markdown(" ") # Parcel
        c6.markdown("") # For buttons
        c7.markdown("") # For status
        c8.markdown("") # For delete

        for section_id, orders in sorted(sections.items()):
            with st.container(border=True):
                c1, c2 = st.columns([0.85, 0.15])
                with c1:
                    st.markdown(f"**Section {section_id}**")
                with c2:
                    st.button(
                        "❌", 
                        key=f"del_sec_{section_id}", 
                        on_click=delete_section, 
                        args=(st.session_state.selected_table, section_id),
                        help="Delete this entire section"
                    )

                section_total = 0

                for o in orders:
                    # id, table_id, section_id, item, qty, status, created_at, price, is_parcel
                    order_id, _, _, item, qty, status, _, price, is_parcel = o
                    if price is None:
                        price = menu_prices_dict.get(item, 0) # Assign price if missing
                    total_price = qty * price
                    section_total += total_price

                    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([3, 1, 1, 1, 1, 2, 2, 1])
                    c1.markdown(f"**{item}** {'🛍️' if is_parcel else ''}")
                    c2.markdown(f"`{qty}`")
                    c3.markdown(f"₹{price:.2f}")
                    c4.markdown(f"**₹{total_price:.2f}**")

                    with c5:
                        disable_parcel_toggle = (status == "Served")
                        if st.button("🛍️", key=f"parcel_{order_id}", help="Toggle Parcel Status", disabled=disable_parcel_toggle):
                            if not disable_parcel_toggle:
                                toggle_parcel_status(order_id)
                    
                    with c6:
                        cc1, cc2 = st.columns(2)
                        disable_qty_buttons = (status == "Served")
                        if cc1.button("➖", key=f"dec_{order_id}", use_container_width=True, disabled=disable_qty_buttons):
                            if not disable_qty_buttons:
                                update_qty(order_id, -1)
                        if cc2.button("➕", key=f"inc_{order_id}", use_container_width=True, disabled=disable_qty_buttons):
                            if not disable_qty_buttons:
                                update_qty(order_id, 1)

                    if status == "Preparing":
                        c7.info("Preparing")
                    elif status == "Ready":
                        c7.button("Mark as Served", key=f"serve_{order_id}", on_click=update_status, args=(order_id, "Served"), use_container_width=True, type="primary")
                    else: # Served
                        c7.success("Served")

                    if status != "Served":
                        c8.button("🗑️", key=f"del_{order_id}", on_click=delete_order, args=(order_id,), use_container_width=True)
                    else:
                        c8.write("")

                st.markdown("---")
                st.markdown(f"<h5 style='text-align: right;'>Section Total: ₹{section_total:.2f}</h5>", unsafe_allow_html=True)
                grand_total += section_total

        if grand_total > 0:
            st.markdown("---")
            st.markdown(f"<h3 style='text-align: right;'>Grand Total: ₹{grand_total:.2f}</h3>", unsafe_allow_html=True)


# ================= KITCHEN VIEW =================
elif view == "Kitchen":
    st.header("🍳 Kitchen View")
    
    # --- Auto-refresh control ---
    if st.sidebar.checkbox("Auto-refresh", value=True):
        st_autorefresh(interval=5000, key="kitchen_refresh")

    # --- Order Filtering ---
    st.sidebar.header("Kitchen Filters")
    filter_status = st.sidebar.multiselect("Filter by Status", ["Preparing", "Ready", "Served"], default=["Preparing", "Ready"])
    
    menu_items_db = get_menu_items()
    item_names = sorted([item[1] for item in menu_items_db])
    filter_items = st.sidebar.multiselect("Filter by Food Item", item_names)

    # --- Display Orders in Columns ---
    all_orders = get_orders(status=filter_status, items=filter_items)
    
    SECTION_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "⚪", "⚫"]

    if not all_orders:
        st.warning("No orders with selected filters.")
    else:
        num_columns = 3
        cols = st.columns(num_columns)
        for i, o in enumerate(all_orders):
            order_id, table_id, section_id, item, qty, status, created_at, _, is_parcel = o
            with cols[i % num_columns].container(border=True):
                emoji = SECTION_EMOJIS[section_id % len(SECTION_EMOJIS)]

                if is_parcel:
                    st.markdown("### 🛍️ PARCEL")

                st.markdown(f"**Table {table_id} | Section {section_id} {emoji}**")
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

# ================= CONFIGURATION VIEW =================
elif view == "Configuration":
    st.header("⚙️ Menu Configuration")

    # --- Add new item ---
    with st.expander("Add New Menu Item", expanded=False):
        with st.form("new_item_form", clear_on_submit=True):
            new_name = st.text_input("Item Name")
            new_price = st.number_input("Price", min_value=0.0, format="%.2f")
            submitted = st.form_submit_button("Add Item")
            if submitted:
                if new_name:
                    if add_menu_item(new_name, new_price):
                        st.success(f"Added '{new_name}' to the menu.")
                        st.rerun()
                    # Error is handled in the function now
                else:
                    st.warning("Item name cannot be empty.")

    st.subheader("Existing Menu Items")
    
    menu_items = get_menu_items()
    if not menu_items:
        st.info("No items in the menu. Add one above.")
    else:
        for item_id, name, price in menu_items:
            with st.container(border=True):
                c1, c2 = st.columns([1,1])
                with c1:
                    st.markdown(f"#### {name}")
                    st.markdown(f"**Price:** ₹{price:.2f}")
                
                with c2:
                    if st.button("Delete Item", key=f"del_{item_id}", use_container_width=True):
                        delete_menu_item(item_id)
                        st.rerun()
                
                with st.expander("Edit Item"):
                    with st.form(f"edit_{item_id}"):
                        new_name = st.text_input("Item Name", value=name)
                        new_price = st.number_input("Price", value=price, min_value=0.0, format="%.2f")
                        if st.form_submit_button("Save Changes", type="primary", use_container_width=True):
                            update_menu_item(item_id, new_name, new_price)
                            st.rerun()
    