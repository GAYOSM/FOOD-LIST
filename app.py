import streamlit as st
import sqlite3
from datetime import datetime
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    # Define a dummy function if the module is not found
    def st_autorefresh(*args, **kwargs):
        st.warning("`streamlit_autorefresh` not found. Auto-refresh will be disabled. Please install it with `pip install streamlit-autorefresh` if you need this feature.")
        pass # Do nothing

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
    if st.sidebar.checkbox("Auto-refresh", value=True):
        st_autorefresh(interval=5000, key="waiter_refresh")

    # --- Table Selection ---
    st.subheader("Select a Table")
    table_options = [str(i) for i in range(1, NUM_TABLES + 1)] # Changed to string for st.radio labels
    
    # Use st.radio for responsive table selection
    selected_table_str = st.radio(
        "Choose Table", 
        table_options, 
        index=st.session_state.selected_table - 1, 
        horizontal=True,
        key="table_selector" # Added a key for st.radio
    )
    st.session_state.selected_table = int(selected_table_str) # Convert back to int
    st.divider() # Add a divider for visual separation
    st.subheader("Current Orders")


    # --- Get all orders for the table and group by section ---
    table_orders = get_orders(table_id=st.session_state.selected_table)
    sections = defaultdict(list)
    for order in table_orders:
        sections[order[2]].append(order) # order[2] is section_id

    # --- Create a price lookup dictionary ---
    menu_prices_dict = {name: price for _, name, price in get_menu_items()}

    # --- Menu and Ordering ---
    with st.expander("Add New Item", expanded=False):
        col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
        with col1:
            menu_item_names = [""] + sorted(list(menu_prices_dict.keys()))
            selected_item = st.selectbox("Select an item", menu_item_names)
        with col2:
            quantity = st.number_input("Quantity", min_value=1, value=1)
            is_parcel_add = st.checkbox("🛍️", key="add_parcel")
        with col3:
            existing_sections = sorted(sections.keys())
            section_options = [f"Section {s}" for s in existing_sections] + ["Create New Section"]
            selected_section_str = st.selectbox("Choose Section", options=section_options)

        with col4:
            st.write("")
            st.write("")
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
        # Calculate grand total for all sections first
        grand_total = 0
        for section_id, orders in sorted(sections.items()):
            section_total_sum = sum(order[7] * order[4] for order in orders if order[7] is not None)
            grand_total += section_total_sum
        
        # Iterate through sections and display each as an expander
        for section_id, orders in sorted(sections.items()):
            with st.expander(f"**Section {section_id}**"):
                with st.container(border=True): # Use container for consistent styling
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

                    section_total_display = 0 
                    for o in orders: # Use 'orders' directly for the current section
                        order_id, _, _, item, qty, status, _, price, is_parcel = o
                        if price is None:
                            price = menu_prices_dict.get(item, 0)
                        total_price = qty * price
                        section_total_display += total_price

                        with st.container(border=False):
                            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                            with c1:
                                st.markdown(f"<p style='font-size:18px;'><b>{item}</b> {'🛍️' if is_parcel else ''}</p>", unsafe_allow_html=True)
                                st.markdown(f"<p style='font-size:12px; color:grey;'>Price: ₹{price:.2f} | Total: ₹{total_price:.2f}</p>", unsafe_allow_html=True)
                            
                            with c2:
                                disable_qty_buttons = (status == "Served")
                                # Use columns directly within c2 for better stacking on mobile
                                qty_col1, qty_col2, qty_col3 = st.columns([1, 2, 1]) 
                                with qty_col1:
                                    if st.button("➖", key=f"dec_{order_id}", use_container_width=True, disabled=disable_qty_buttons):
                                        if not disable_qty_buttons:
                                            update_qty(order_id, -1)
                                with qty_col2:
                                    st.markdown(f"<div style='text-align: center; padding-top: 0px; font-size:18px;'><b>`{qty}`</b></div>", unsafe_allow_html=True)
                                with qty_col3:
                                    if st.button("➕", key=f"inc_{order_id}", use_container_width=True, disabled=disable_qty_buttons):
                                        if not disable_qty_buttons:
                                            update_qty(order_id, 1)

                            with c3:
                                if status == "Preparing":
                                    st.markdown("<p style='color:orange; font-size:18px;'><b>Preparing</b></p>", unsafe_allow_html=True)
                                elif status == "Ready":
                                    st.button("Mark as Served", key=f"serve_{order_id}", on_click=update_status, args=(order_id, "Served"), use_container_width=True, type="primary")
                                else:
                                    st.markdown("<p style='color:lightgreen; font-size:18px;'><b>Served</b></p>", unsafe_allow_html=True)
                            
                            with c4:
                                if status != "Served":
                                    disable_buttons = (status == "Served")
                                    col_parcel, col_delete = st.columns(2) # Create two columns for the buttons
                                    with col_parcel:
                                        if st.button("🛍️", key=f"parcel_{order_id}", help="Toggle Parcel Status", disabled=disable_buttons, use_container_width=True):
                                            if not disable_buttons:
                                                toggle_parcel_status(order_id)
                                    with col_delete:
                                        if st.button("🗑️", key=f"del_{order_id}", use_container_width=True, help="Delete this item"):
                                            delete_order(order_id)
                        st.divider()


                    st.markdown(f"<h5 style='text-align: right;'>Section Total: ₹{section_total_display:.2f}</h5>", unsafe_allow_html=True)
                
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
        num_columns = 2 # Changed for better mobile responsiveness
        cols = st.columns(num_columns)
        for i, o in enumerate(all_orders):
            order_id, table_id, section_id, item, qty, status, created_at, _, is_parcel = o
            with cols[i % num_columns].container(border=True):
                emoji = SECTION_EMOJIS[section_id % len(SECTION_EMOJIS)]

                if is_parcel:
                    st.markdown("### 🛍️ PARCEL")

                st.markdown(f"**Table {table_id} | Section {section_id} {emoji}**")
                st.markdown(f"### **{qty} x {item}**")
                st.caption(f"Ordered at: {created_at}")
                
                if status == "Preparing":
                    st.markdown("<p style='color:orange; font-size:18px;'><b>Status: Preparing...</b></p>", unsafe_allow_html=True)
                    if st.button("Mark as Ready", key=f"kitchen_ready_{order_id}", use_container_width=True, type="primary"):
                        update_status(order_id, "Ready")
                elif status == "Ready":
                    st.markdown("<p style='color:yellow; font-size:18px;'><b>Status: ✅Ready</b></p>", unsafe_allow_html=True)
                else: 
                    st.markdown("<p style='color:lightgreen; font-size:18px;'><b>Status: Served</b></p>", unsafe_allow_html=True)

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
        num_columns = 2 # Match Kitchen view responsiveness
        cols = st.columns(num_columns)
        for i, (item_id, name, price) in enumerate(menu_items):
            with cols[i % num_columns].container(border=True):
                st.markdown(f"#### {name}")
                st.markdown(f"**Price:** ₹{price:.2f}")
                
                # Action buttons
                col_del, col_edit_exp = st.columns([1,1])
                with col_del:
                    if st.button("Delete Item", key=f"cfg_del_{item_id}", use_container_width=True): # Changed key to avoid conflicts
                        delete_menu_item(item_id)
                        st.rerun()
                
                with col_edit_exp:
                    # The Edit Expander will be placed here
                    with st.expander("Edit Item"):
                        with st.form(f"cfg_edit_form_{item_id}", clear_on_submit=False): # Changed key
                            edited_name = st.text_input("Item Name", value=name, key=f"cfg_edit_name_{item_id}")
                            edited_price = st.number_input("Price", value=price, min_value=0.0, format="%.2f", key=f"cfg_edit_price_{item_id}")
                            if st.form_submit_button("Save Changes", type="primary", use_container_width=True):
                                if update_menu_item(item_id, edited_name, edited_price):
                                    st.success(f"Updated '{edited_name}'.")
                                    st.rerun()
    