# main.py
# Final Kivy app: delivery + empty reconciliation (mandatory reason) + view by date table + export
# Requirements: kivy, sqlite3 (builtin). Optional: openpyxl for xlsx export.
# Run: python main.py

import sqlite3
from datetime import datetime, date
import os
import csv
import calendar

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

# Optional openpyxl
try:
    from openpyxl import Workbook
    HAVE_OPENPYXL = True
except Exception:
    HAVE_OPENPYXL = False

# Window size for desktop testing
Window.size = (460, 820)

# ---------------- Database setup ----------------
DB = "delivery_final.db"
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

# Create base tables if not exist
cur.execute("""
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee TEXT,
    total_cyl INTEGER,
    empty_received INTEGER,
    online_pay INTEGER,
    paytm_pay INTEGER,
    partial_amt REAL,
    final_amt REAL,
    collected_amt REAL,
    date_time TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS remarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER,
    seq INTEGER,
    remark_type TEXT,
    consumer_name TEXT,
    created_at TEXT,
    FOREIGN KEY(record_id) REFERENCES records(id)
)
""")
conn.commit()

# If older DB doesn't have empty_received column (rare), try to add (safe)
try:
    cur.execute("SELECT empty_received FROM records LIMIT 1")
except sqlite3.OperationalError:
    try:
        cur.execute("ALTER TABLE records ADD COLUMN empty_received INTEGER")
        conn.commit()
    except Exception:
        pass

# Settings helper
def get_setting(k, default=None):
    cur.execute("SELECT value FROM settings WHERE key=?", (k,))
    r = cur.fetchone()
    return r[0] if r else default

def set_setting(k, v):
    cur.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (k, str(v)))
    conn.commit()

if get_setting("cylinder_price") is None:
    set_setting("cylinder_price", "877.5")

def get_price():
    return float(get_setting("cylinder_price", "877.5"))

# Employees helper
def get_employees():
    cur.execute("SELECT name FROM employees ORDER BY name")
    return [r[0] for r in cur.fetchall()]

if not get_employees():
    try:
        cur.execute("INSERT INTO employees (name) VALUES (?)", ("ABC Employee",))
        cur.execute("INSERT INTO employees (name) VALUES (?)", ("XYZ Employee",))
        conn.commit()
    except:
        pass

# ---------------- UI helpers ----------------
def make_label(text, size_hint=(0.6,1), halign="left", valign="middle", font_size=14):
    lbl = Label(text=str(text), size_hint=size_hint, halign=halign, valign=valign, font_size=font_size)
    lbl.bind(size=lbl.setter("text_size"))
    return lbl

def create_row(label_text, widget, label_hint=(0.55,1), height=44):
    row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=height, spacing=8)
    lbl = make_label(label_text, size_hint=label_hint)
    widget.size_hint = (1 - label_hint[0], 1)
    row.add_widget(lbl)
    row.add_widget(widget)
    return row

# ---------------- Screens ----------------
class MainMenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        box = BoxLayout(orientation="vertical", padding=12, spacing=10)
        box.add_widget(Label(text="Cylinder Collector (Final)", font_size=24, size_hint=(1,None), height=60))

        b1 = Button(text="1. New Delivery Entry", size_hint=(1, None), height=48)
        b1.bind(on_release=lambda x: self.goto("entry"))
        box.add_widget(b1)

        b2 = Button(text="2. Add Delivery Boy", size_hint=(1, None), height=48)
        b2.bind(on_release=lambda x: self.goto("add_employee"))
        box.add_widget(b2)

        b3 = Button(text="3. Change Cylinder Price", size_hint=(1, None), height=48)
        b3.bind(on_release=lambda x: self.goto("change_price"))
        box.add_widget(b3)

        b4 = Button(text="4. View Records by Date", size_hint=(1, None), height=48)
        b4.bind(on_release=lambda x: self.goto("view_by_date"))
        box.add_widget(b4)

        box.add_widget(Label(text="Data stored locally (SQLite). Export: Excel/CSV.", font_size=12, size_hint=(1,None), height=30))
        self.add_widget(box)

    def goto(self, s):
        self.manager.current = s

class NewEntryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.final_amount = 0.0

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        top = BoxLayout(size_hint=(1, None), height=44)
        top.add_widget(Button(text="← Back", size_hint=(0.28,1), on_release=lambda x: self.manager.switch_to(self.manager.get_screen("menu"))))
        top.add_widget(Label(text="New Delivery Entry", font_size=18))
        root.add_widget(top)

        root.add_widget(make_label("Delivery Boy:", font_size=15, size_hint=(1, None)))
        self.emp_spinner = Spinner(text="Choose", values=get_employees(), size_hint=(1, None), height=40)
        root.add_widget(self.emp_spinner)

        self.total_input = TextInput(input_filter="int", multiline=False)
        root.add_widget(create_row("Total Cylinders:", self.total_input))

        # empty Received initially prefilled with delivered value, user can change in popup flow
        self.empty_input = TextInput(input_filter="int", multiline=False, text="0")
        root.add_widget(create_row("Empty Received (will be asked after submit):", self.empty_input))

        self.online_input = TextInput(input_filter="int", multiline=False, text="0")
        root.add_widget(create_row("Online (full) count:", self.online_input))

        self.paytm_input = TextInput(input_filter="int", multiline=False, text="0")
        root.add_widget(create_row("PayTM (full) count:", self.paytm_input))

        self.partial_input = TextInput(input_filter="float", multiline=False, text="0")
        root.add_widget(create_row("Partial PayTM total (₹):", self.partial_input))

        calc = Button(text="Calculate Amount", size_hint=(1, None), height=44)
        calc.bind(on_release=self.calculate)
        root.add_widget(calc)

        self.final_label = Label(text="Amount to collect: ₹ 0.00", font_size=18, size_hint=(1,None), height=40)
        root.add_widget(self.final_label)

        # Amount collected row fixed using create_row (ensures visibility)
        self.collected_input = TextInput(input_filter="float", multiline=False)
        root.add_widget(create_row("Amount collected (₹):", self.collected_input))

        submit = Button(text="Submit & Reconcile Empties", size_hint=(1, None), height=48)
        submit.bind(on_release=self.on_submit)
        root.add_widget(submit)

        self.add_widget(root)

    def refresh_employees(self):
        self.emp_spinner.values = get_employees()
        if self.emp_spinner.text not in self.emp_spinner.values:
            self.emp_spinner.text = "Choose"

    def calculate(self, instance):
        try:
            total = int(self.total_input.text or 0)
            online = int(self.online_input.text or 0)
            paytm = int(self.paytm_input.text or 0)
            partial = float(self.partial_input.text or 0.0)

            if online + paytm > total:
                self.show_popup("Input error", "Online + PayTM full count cannot exceed total deliveries.")
                return

            cash_cylinders = total - online - paytm
            price = get_price()
            cash_amount = cash_cylinders * price
            final = round(cash_amount + partial, 2)

            self.final_amount = final
            self.final_label.text = f"Amount to collect: ₹ {final:,.2f}"
        except Exception as e:
            self.show_popup("Error", f"Invalid input. {e}")

    def on_submit(self, instance):
        # ensure calculation done
        try:
            self.calculate(None)
        except:
            pass

        try:
            collected = float(self.collected_input.text or 0.0)
        except:
            collected = 0.0

        final = getattr(self, "final_amount", 0.0)

        emp = self.emp_spinner.text if self.emp_spinner.text != "Choose" else ""
        delivered = int(self.total_input.text or 0)
        # If user filled empty_input in form, use it as initial suggested value; else default to delivered
        try:
            pre_empty = int(self.empty_input.text or delivered)
        except:
            pre_empty = delivered

        try:
            cur.execute("""
            INSERT INTO records (employee, total_cyl, empty_received, online_pay, paytm_pay, partial_amt, final_amt, collected_amt, date_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                emp,
                delivered,
                pre_empty,
                int(self.online_input.text or 0),
                int(self.paytm_input.text or 0),
                float(self.partial_input.text or 0.0),
                float(final),
                float(collected),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            rec_id = cur.lastrowid
        except Exception as e:
            self.show_popup("DB Error", str(e))
            return

        # After saving record, open reconciliation if empties != delivered or to allow editing empties
        # We will read stored empty_received and compare
        cur.execute("SELECT empty_received FROM records WHERE id=?", (rec_id,))
        rr = cur.fetchone()
        stored_empty = int(rr[0]) if rr and rr[0] is not None else delivered

        # If empty != delivered then we must reconcile reasons; if equal, still allow user to open reconcile popup (but since you chose "immediate", we will open)
        # Open ReconcilePopup with delivered and stored_empty
        rp = ReconcilePopup(self.manager, rec_id, delivered, stored_empty)
        rp.open()

    def show_popup(self, title, msg):
        Popup(title=title, content=Label(text=msg), size_hint=(0.8, 0.3)).open()

class AddEmployeeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=12, spacing=10)
        top = BoxLayout(size_hint=(1, None), height=44)
        top.add_widget(Button(text="← Back", size_hint=(0.28, 1), on_release=lambda x: self.manager.switch_to(self.manager.get_screen("menu"))))
        top.add_widget(Label(text="Add Delivery Boy", font_size=18))
        root.add_widget(top)

        root.add_widget(make_label("Name:", size_hint=(1, None), font_size=14))
        self.name_input = TextInput(multiline=False)
        root.add_widget(self.name_input)

        add_btn = Button(text="Add", size_hint=(1, None), height=44)
        add_btn.bind(on_release=self.add_employee)
        root.add_widget(add_btn)

        self.msg_label = Label(text="", size_hint=(1, None), height=30)
        root.add_widget(self.msg_label)

        self.add_widget(root)

    def add_employee(self, instance):
        name = (self.name_input.text or "").strip()
        if not name:
            self.msg_label.text = "Enter a valid name."
            return
        try:
            cur.execute("INSERT INTO employees (name) VALUES (?)", (name,))
            conn.commit()
            self.msg_label.text = "Added successfully."
            self.name_input.text = ""
            if "entry" in self.manager.screen_names:
                self.manager.get_screen("entry").refresh_employees()
        except sqlite3.IntegrityError:
            self.msg_label.text = "Name already exists."
        except Exception as e:
            self.msg_label.text = f"Error: {e}"

class ChangePriceScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=12, spacing=10)
        top = BoxLayout(size_hint=(1,None), height=44)
        top.add_widget(Button(text="← Back", size_hint=(0.28,1), on_release=lambda x: self.manager.switch_to(self.manager.get_screen("menu"))))
        top.add_widget(Label(text="Change Cylinder Price", font_size=18))
        root.add_widget(top)

        root.add_widget(make_label("Current price (₹):", size_hint=(1,None), font_size=14))
        self.price_input = TextInput(text=str(get_price()), input_filter="float", multiline=False)
        root.add_widget(self.price_input)

        save_btn = Button(text="Save Price", size_hint=(1, None), height=44)
        save_btn.bind(on_release=self.save_price)
        root.add_widget(save_btn)

        self.msg = Label(text="", size_hint=(1, None), height=30)
        root.add_widget(self.msg)

        self.add_widget(root)

    def save_price(self, instance):
        try:
            val = float(self.price_input.text)
            set_setting("cylinder_price", val)
            self.msg.text = "Price updated."
        except Exception as e:
            self.msg.text = f"Invalid value: {e}"

# ---------------- Reconcile Popup (mandatory selection) ----------------
class ReconcilePopup(Popup):
    """
    Opens immediately after record saved. Shows empties received value and if differs from delivered,
    presents a multi-step mandatory selection UI for each extra/missing cylinder.
    """
    def __init__(self, manager, record_id, delivered_count, empty_received_count, **kwargs):
        super().__init__(title="Empty Cylinder Reconciliation", size_hint=(0.95,0.9), **kwargs)
        self.manager = manager
        self.record_id = record_id
        self.delivered = int(delivered_count or 0)
        self.empty_received = int(empty_received_count or 0)
        # compute difference: positive -> extra received, negative -> missing
        self.diff = self.empty_received - self.delivered
        self.steps = []
        self.current_index = 0

        self.body = BoxLayout(orientation="vertical", padding=10, spacing=8)
        self.info = Label(text=f"Delivered: {self.delivered}  |  Empty received: {self.empty_received}", size_hint=(1, None), height=36)
        self.body.add_widget(self.info)

        # allow user to edit empty_received value before proceeding (update records if changed)
        edit_row = BoxLayout(size_hint=(1, None), height=44, spacing=8)
        edit_row.add_widget(Label(text="Edit empties received (if wrong):", size_hint=(0.6,1)))
        self.empty_edit = TextInput(text=str(self.empty_received), input_filter="int", multiline=False, size_hint=(0.4,1))
        edit_row.add_widget(self.empty_edit)
        self.body.add_widget(edit_row)

        control_row = BoxLayout(size_hint=(1, None), height=44, spacing=8)
        btn_update = Button(text="Update & Proceed")
        btn_update.bind(on_release=self.update_and_prepare)
        btn_skip = Button(text="Skip (close)")
        btn_skip.bind(on_release=self.dismiss)
        control_row.add_widget(btn_skip)
        control_row.add_widget(btn_update)
        self.body.add_widget(control_row)

        self.content = self.body

    def update_and_prepare(self, inst):
        # update empty_received based on edit field and save to record
        try:
            new_empty = int(self.empty_edit.text or 0)
        except:
            Popup(title="Error", content=Label(text="Invalid empties count"), size_hint=(0.6,0.3)).open()
            return
        # update DB
        try:
            cur.execute("UPDATE records SET empty_received=? WHERE id=?", (new_empty, self.record_id))
            conn.commit()
            self.empty_received = new_empty
        except Exception as e:
            Popup(title="DB Error", content=Label(text=str(e)), size_hint=(0.7,0.3)).open()
            return

        # recalc diff and prepare steps if needed
        self.diff = self.empty_received - self.delivered
        self.steps = []
        if self.diff == 0:
            # nothing else required
            Popup(title="Info", content=Label(text="Empty count equals delivered — no remarks required."), size_hint=(0.7,0.3)).open()
            self.dismiss()
            return
        elif self.diff < 0:
            # missing empties -> need reasons for missing
            missing = abs(self.diff)
            for i in range(missing):
                self.steps.append({"seq": i+1, "mode": "missing", "options": ["NC","DBC","TV","Empty baki"], "selected": None, "consumer": ""})
        else:
            # extra empties -> user chooses reason per extra
            extra = self.diff
            for i in range(extra):
                # allow both options; the user chooses
                self.steps.append({"seq": i+1, "mode": "extra", "options": ["TV","Empty Return","NC","DBC","Empty baki"], "selected": None, "consumer": ""})

        # open steps UI
        self.open_steps_ui()

    def open_steps_ui(self):
        # clear and build step UI
        self.body.clear_widgets()
        self.step_title = Label(text=f"Enter details for each {'missing' if self.diff<0 else 'extra'} cylinder (mandatory selection)", size_hint=(1,None), height=36)
        self.body.add_widget(self.step_title)

        self.form_box = BoxLayout(orientation="vertical", spacing=8)
        self.drop = Spinner(text="Choose reason", values=self.steps[0]["options"], size_hint=(1,None), height=44)
        self.name_input = TextInput(hint_text="Consumer name (required for NC/DBC/TV else optional)", multiline=False)
        self.form_box.add_widget(self.drop)
        self.form_box.add_widget(self.name_input)
        self.body.add_widget(self.form_box)

        # nav
        nav = BoxLayout(size_hint=(1,None), height=44, spacing=8)
        self.prev_btn = Button(text="Previous")
        self.next_btn = Button(text="Next")
        nav.add_widget(self.prev_btn)
        nav.add_widget(self.next_btn)
        self.body.add_widget(nav)

        # bottom actions
        bottom = BoxLayout(size_hint=(1,None), height=48, spacing=8)
        self.cancel_btn = Button(text="Cancel")
        self.save_btn = Button(text="Save & Close")
        bottom.add_widget(self.cancel_btn)
        bottom.add_widget(self.save_btn)
        self.body.add_widget(bottom)

        # bindings
        self.prev_btn.bind(on_release=self.go_prev)
        self.next_btn.bind(on_release=self.go_next)
        self.cancel_btn.bind(on_release=self.dismiss)
        self.save_btn.bind(on_release=self.save_all)

        self.current_index = 0
        self.load_step(0)

    def load_step(self, idx):
        if idx<0 or idx>=len(self.steps):
            return
        s = self.steps[idx]
        self.drop.values = s["options"]
        self.drop.text = s["selected"] if s["selected"] else "Choose reason"
        self.name_input.text = s.get("consumer","")
        self.step_title.text = f"Entry {idx+1} of {len(self.steps)} - {'missing' if s['mode']=='missing' else 'extra'}"

    def save_current(self):
        s = self.steps[self.current_index]
        sel = self.drop.text if self.drop.text != "Choose reason" else None
        s["selected"] = sel
        s["consumer"] = self.name_input.text.strip()

    def go_next(self, inst):
        self.save_current()
        # require selection before moving forward
        if not self.steps[self.current_index].get("selected"):
            Popup(title="Required", content=Label(text="Please select a reason before proceeding."), size_hint=(0.7,0.3)).open()
            return
        self.current_index = min(self.current_index+1, len(self.steps)-1)
        self.load_step(self.current_index)

    def go_prev(self, inst):
        self.save_current()
        self.current_index = max(self.current_index-1, 0)
        self.load_step(self.current_index)

    def save_all(self, inst):
        # ensure current saved and all steps have a selection
        self.save_current()
        for s in self.steps:
            if not s.get("selected"):
                Popup(title="Required", content=Label(text="All entries must have a reason selected before saving."), size_hint=(0.8,0.35)).open()
                return
        # persist steps
        try:
            for s in self.steps:
                cur.execute("""
                INSERT INTO remarks (record_id, seq, remark_type, consumer_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    self.record_id,
                    s["seq"],
                    s["selected"] or "",
                    s["consumer"] or "",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
            conn.commit()
            Popup(title="Saved", content=Label(text="Reconciliation saved."), size_hint=(0.7,0.3)).open()
            self.dismiss()
        except Exception as e:
            Popup(title="Error", content=Label(text=str(e)), size_hint=(0.8,0.35)).open()

# ---------------- Calendar popup ----------------
class CalendarPopup(Popup):
    def __init__(self, on_date_selected, initial_date=None, **kwargs):
        super().__init__(title="Select Date", size_hint=(0.95,0.85), **kwargs)
        self.on_date_selected = on_date_selected
        self.selected_date = initial_date or date.today()
        self.body = BoxLayout(orientation="vertical", padding=8, spacing=8)
        self.header = BoxLayout(size_hint=(1,None), height=40)
        self.btn_prev = Button(text="<", size_hint=(0.12,1))
        self.btn_next = Button(text=">", size_hint=(0.12,1))
        self.lbl_month = Label(text="", size_hint=(0.76,1))
        self.header.add_widget(self.btn_prev)
        self.header.add_widget(self.lbl_month)
        self.header.add_widget(self.btn_next)
        self.body.add_widget(self.header)

        self.calendar_grid = GridLayout(cols=7, spacing=4, size_hint=(1,None))
        self.calendar_grid.bind(minimum_height=self.calendar_grid.setter('height'))
        self.body.add_widget(self.calendar_grid)

        btn_choose = Button(text="Choose", size_hint=(1,None), height=44)
        btn_choose.bind(on_release=self.choose_date)
        self.body.add_widget(btn_choose)

        self.content = self.body
        self.btn_prev.bind(on_release=lambda x: self.change_month(-1))
        self.btn_next.bind(on_release=lambda x: self.change_month(1))
        self.render_calendar()

    def change_month(self, delta):
        y = self.selected_date.year; m = self.selected_date.month + delta
        if m<1: m=12; y-=1
        if m>12: m=1; y+=1
        day = min(self.selected_date.day, calendar.monthrange(y,m)[1])
        self.selected_date = date(y,m,day)
        self.render_calendar()

    def render_calendar(self):
        self.calendar_grid.clear_widgets()
        y = self.selected_date.year; m = self.selected_date.month
        self.lbl_month.text = f"{calendar.month_name[m]} {y}"
        for wd in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]:
            lbl = Label(text=wd, size_hint=(1,None), height=28)
            lbl.bind(size=lbl.setter("text_size"))
            self.calendar_grid.add_widget(lbl)
        month_calendar = calendar.monthcalendar(y,m)
        for week in month_calendar:
            for d in week:
                if d==0:
                    self.calendar_grid.add_widget(Label(text="", size_hint_y=None, height=36))
                else:
                    btn = Button(text=str(d), size_hint_y=None, height=36)
                    btn.bind(on_release=lambda inst, day=d: self.on_day_pressed(day))
                    self.calendar_grid.add_widget(btn)

    def on_day_pressed(self, day):
        self.selected_date = date(self.selected_date.year, self.selected_date.month, day)
        self.render_calendar()

    def choose_date(self, _):
        sel = self.selected_date.strftime("%Y-%m-%d")
        self.dismiss()
        self.on_date_selected(sel)

# ---------------- View By Date Screen (table + totals + empty_received) ----------------
class ViewByDateScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_selected_date = datetime.now().strftime("%Y-%m-%d")
        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        top = BoxLayout(size_hint=(1,None), height=44)
        top.add_widget(Button(text="← Back", size_hint=(0.28,1), on_release=lambda x: self.manager.switch_to(self.manager.get_screen("menu"))))
        top.add_widget(Label(text="View Records by Date", font_size=18))
        root.add_widget(top)

        # date selector row with dd-mm-yyyy display
        row = BoxLayout(size_hint=(1,None), height=44, spacing=8)
        self.date_label = Label(text=f"Date: {self.format_ddmmyyyy(self.current_selected_date)}", size_hint=(0.6,1))
        row.add_widget(self.date_label)
        row.add_widget(Button(text="Pick Date", size_hint=(0.4,1), on_release=self.open_calendar))
        root.add_widget(row)

        # export + refresh
        er = BoxLayout(size_hint=(1,None), height=44, spacing=8)
        er.add_widget(Button(text="Export (xlsx/csv)", on_release=self.export_current))
        er.add_widget(Button(text="Refresh", on_release=lambda x: self.load_records(self.current_selected_date)))
        root.add_widget(er)

        # table header (scrollable)
        self.scroll = ScrollView()
        self.table_box = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=6)
        self.table_box.bind(minimum_height=self.table_box.setter('height'))
        self.scroll.add_widget(self.table_box)
        root.add_widget(self.scroll)

        # totals area
        self.totals_box = BoxLayout(orientation="vertical", size_hint=(1,None), height=160, padding=6, spacing=6)
        root.add_widget(self.totals_box)

        root.add_widget(Label(text="(Export uses openpyxl if installed, else CSV)", size_hint=(1,None), height=24))
        self.add_widget(root)
        self.load_records(self.current_selected_date)

    def format_ddmmyyyy(self, iso_yyyy_mm_dd):
        if not iso_yyyy_mm_dd:
            return ""
        try:
            if " " in iso_yyyy_mm_dd:
                dt = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d")
            return dt.strftime("%d-%m-%Y")
        except:
            try:
                dt = datetime.strptime(iso_yyyy_mm_dd[:10], "%Y-%m-%d")
                return dt.strftime("%d-%m-%Y")
            except:
                return iso_yyyy_mm_dd

    def open_calendar(self, inst):
        initial = datetime.strptime(self.current_selected_date, "%Y-%m-%d").date()
        cal = CalendarPopup(self.on_date_selected, initial_date=initial)
        cal.open()

    def on_date_selected(self, yyyy_mm_dd):
        self.current_selected_date = yyyy_mm_dd
        self.date_label.text = f"Date: {self.format_ddmmyyyy(yyyy_mm_dd)}"
        self.load_records(yyyy_mm_dd)

    def load_records(self, yyyy_mm_dd):
        self.table_box.clear_widgets()
        self.totals_box.clear_widgets()
        like = yyyy_mm_dd + "%"
        cur.execute("""
        SELECT id, employee, total_cyl, empty_received, online_pay, paytm_pay, partial_amt, final_amt, collected_amt, date_time
        FROM records WHERE date_time LIKE ? ORDER BY id
        """, (like,))
        rows = cur.fetchall()

        if not rows:
            self.table_box.add_widget(Label(text="No records for this date.", size_hint_y=None, height=40))
            return

        # Table Header row (columns)
        header = GridLayout(cols=8, size_hint_y=None, height=36)
        header_cols = ["Sr", "Cyl Delivered", "Empty Received", "Online", "Paytm", "Add Paytm", "Cash Collected", "Remarks"]
        for h in header_cols:
            lbl = Label(text=f"[b]{h}[/b]", markup=True)
            lbl.bind(size=lbl.setter("text_size"))
            header.add_widget(lbl)
        self.table_box.add_widget(header)

        # Totals accumulators
        tot_cyl = 0
        tot_empty = 0
        tot_online = 0
        tot_paytm = 0
        tot_add_paytm = 0.0
        tot_cash = 0.0

        # For each record render one table row
        for idx, r in enumerate(rows, start=1):
            rec_id, emp, total_cyl, empty_received, online_pay, paytm_pay, partial_amt, final_amt, collected_amt, dt = r
            tot_cyl += int(total_cyl or 0)
            tot_empty += int(empty_received or 0)
            tot_online += int(online_pay or 0)
            tot_paytm += int(paytm_pay or 0)
            tot_add_paytm += float(partial_amt or 0.0)
            tot_cash += float(collected_amt or 0.0)

            # fetch remarks for this record and format as "TYPE:NAME, TYPE:NAME"
            cur.execute("SELECT remark_type, consumer_name FROM remarks WHERE record_id=? ORDER BY seq", (rec_id,))
            rem_rows = cur.fetchall()
            remarks_list = []
            for rt, cn in rem_rows:
                if cn and cn.strip():
                    remarks_list.append(f"{rt}: {cn}")
                else:
                    remarks_list.append(f"{rt}")
            remarks_text = ", ".join(remarks_list) if remarks_list else ""

            row = GridLayout(cols=8, size_hint_y=None, height=40)
            row.add_widget(Label(text=str(idx)))
            row.add_widget(Label(text=str(total_cyl)))
            row.add_widget(Label(text=str(empty_received)))
            row.add_widget(Label(text=str(online_pay)))
            row.add_widget(Label(text=str(paytm_pay)))
            row.add_widget(Label(text=f"₹{partial_amt:.2f}" if partial_amt is not None else "₹0.00"))
            row.add_widget(Label(text=f"₹{collected_amt:.2f}" if collected_amt is not None else "₹0.00"))
            row.add_widget(Label(text=remarks_text))
            for child in row.children:
                child.bind(size=child.setter("text_size"))
            self.table_box.add_widget(row)

        # Totals separator
        self.table_box.add_widget(Label(text=" ", size_hint_y=None, height=8))

        # Totals summary below table (as requested)
        tot_box = GridLayout(cols=1, size_hint_y=None, height=160, spacing=6)
        tot_box.add_widget(Label(text=f"Total Cylinders Delivered: {tot_cyl}", size_hint_y=None, height=28))
        tot_box.add_widget(Label(text=f"Total Empty Received: {tot_empty}", size_hint_y=None, height=28))
        tot_box.add_widget(Label(text=f"Total Online Count: {tot_online}", size_hint_y=None, height=28))
        tot_box.add_widget(Label(text=f"Total Paytm Count: {tot_paytm}", size_hint_y=None, height=28))
        tot_box.add_widget(Label(text=f"Total Additional Paytm Amount: ₹{tot_add_paytm:,.2f}", size_hint_y=None, height=28))
        tot_box.add_widget(Label(text=f"Total Cash Collected: ₹{tot_cash:,.2f}", size_hint_y=None, height=28))
        self.totals_box.add_widget(tot_box)

    def export_current(self, inst):
        yyyy_mm_dd = self.current_selected_date
        like = yyyy_mm_dd + "%"
        cur.execute("""
        SELECT id, employee, total_cyl, empty_received, online_pay, paytm_pay, partial_amt, final_amt, collected_amt, date_time
        FROM records WHERE date_time LIKE ? ORDER BY id
        """, (like,))
        rows = cur.fetchall()
        if not rows:
            Popup(title="Export", content=Label(text="No records to export for this date."), size_hint=(0.7,0.3)).open()
            return

        folder = os.path.abspath(".")
        fname_base = f"records_{yyyy_mm_dd}"
        if HAVE_OPENPYXL:
            fname = os.path.join(folder, fname_base + ".xlsx")
            try:
                wb = Workbook()
                ws = wb.active
                ws.append(["Sr","employee","total_cyl","empty_received","online_pay","paytm_pay","partial_amt","final_amt","collected_amt","date_time","remarks"])
                for idx, r in enumerate(rows, start=1):
                    rec_id = r[0]
                    cur.execute("SELECT remark_type, consumer_name FROM remarks WHERE record_id=? ORDER BY seq", (rec_id,))
                    rem = ", ".join([f"{rt}: {cn}" if cn else rt for rt,cn in cur.fetchall()]) or ""
                    ws.append([idx, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], rem])
                # append totals at bottom
                tot_cyl = sum(int(r[2] or 0) for r in rows)
                tot_empty = sum(int(r[3] or 0) for r in rows)
                tot_online = sum(int(r[4] or 0) for r in rows)
                tot_paytm = sum(int(r[5] or 0) for r in rows)
                tot_add = sum(float(r[6] or 0.0) for r in rows)
                tot_cash = sum(float(r[8] or 0.0) for r in rows)
                ws.append([])
                ws.append(["TOTALS", "", tot_cyl, tot_empty, tot_online, tot_paytm, tot_add, "", tot_cash, "", ""])
                wb.save(fname)
                Popup(title="Exported", content=Label(text=f"Exported to {fname}"), size_hint=(0.8,0.3)).open()
            except Exception as e:
                Popup(title="Export Error", content=Label(text=str(e)), size_hint=(0.8,0.3)).open()
        else:
            fname = os.path.join(folder, fname_base + ".csv")
            try:
                with open(fname, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Sr","employee","total_cyl","empty_received","online_pay","paytm_pay","partial_amt","final_amt","collected_amt","date_time","remarks"])
                    for idx, r in enumerate(rows, start=1):
                        rec_id = r[0]
                        cur.execute("SELECT remark_type, consumer_name FROM remarks WHERE record_id=? ORDER BY seq", (rec_id,))
                        rem = ", ".join([f"{rt}: {cn}" if cn else rt for rt,cn in cur.fetchall()]) or ""
                        writer.writerow([idx, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], rem])
                    # totals
                    tot_cyl = sum(int(r[2] or 0) for r in rows)
                    tot_empty = sum(int(r[3] or 0) for r in rows)
                    tot_online = sum(int(r[4] or 0) for r in rows)
                    tot_paytm = sum(int(r[5] or 0) for r in rows)
                    tot_add = sum(float(r[6] or 0.0) for r in rows)
                    tot_cash = sum(float(r[8] or 0.0) for r in rows)
                    writer.writerow([])
                    writer.writerow(["TOTALS", "", tot_cyl, tot_empty, tot_online, tot_paytm, tot_add, "", tot_cash, "", ""])
                Popup(title="Exported", content=Label(text=f"Exported to {fname} (CSV)"), size_hint=(0.8,0.3)).open()
            except Exception as e:
                Popup(title="Export Error", content=Label(text=str(e)), size_hint=(0.8,0.3)).open()

# ---------------- App bootstrap ----------------
class DeliveryApp(App):
    def build(self):
        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(MainMenuScreen(name="menu"))
        sm.add_widget(NewEntryScreen(name="entry"))
        sm.add_widget(AddEmployeeScreen(name="add_employee"))
        sm.add_widget(ChangePriceScreen(name="change_price"))
        sm.add_widget(ViewByDateScreen(name="view_by_date"))
        return sm

if __name__ == "__main__":
    DeliveryApp().run()

