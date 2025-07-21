import tkinter as tk
from tkinter import messagebox, simpledialog, TclError
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.patches as patches
import random
import textwrap

# --- Data Class for a Room ---
class Room:
    """Represents a single room with position and dimensions."""
    def __init__(self, name, x, y, width, height):
        self.update_state((name, x, y, width, height))

    def get_state(self):
        return (self.name, self.x, self.y, self.width, self.height)

    def update_state(self, state_tuple):
        self.name, self.x, self.y, self.width, self.height = state_tuple

    def contains(self, px, py):
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def get_resize_handle(self, px, py, tolerance=5): #! MODIFIED: Increased tolerance for easier grabbing
        l, r, b, t = self.x, self.x + self.width, self.y, self.y + self.height
        on_l, on_r = abs(px - l) < tolerance, abs(px - r) < tolerance
        on_b, on_t = abs(py - b) < tolerance, abs(py - t) < tolerance

        # Prioritize corners
        if on_t and on_l: return 'top-left'
        if on_t and on_r: return 'top-right'
        if on_b and on_l: return 'bottom-left'
        if on_b and on_r: return 'bottom-right'
        # Then edges
        if on_t: return 'top'
        if on_b: return 'bottom'
        if on_l: return 'left'
        if on_r: return 'right'
        return None

# --- Data Class for a Blueprint Object (e.g., furniture) ---
class BlueprintObject:
    """Represents a single object like furniture."""
    def __init__(self, name, x, y, width, height):
        self.update_state((name, x, y, width, height))

    def get_state(self):
        return (self.name, self.x, self.y, self.width, self.height)

    def update_state(self, state_tuple):
        self.name, self.x, self.y, self.width, self.height = state_tuple

    def contains(self, px, py):
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

# --- Base Dialog Class ---
class BaseDialog(tk.Toplevel):
    """A base class for our dialogs to reduce code duplication."""
    def __init__(self, parent, title, fields, existing_state=None, name_readonly=False):
        super().__init__(parent)
        self.transient(parent)
        self.result = None
        self.title(title)
        self.geometry("350x380")

        body = ttk.Frame(self, padding="15")
        body.pack(expand=True, fill=tk.BOTH)

        self.entries = {}
        for i, field in enumerate(fields):
            ttk.Label(body, text=f"{field}:").grid(row=i, column=0, sticky=tk.W, padx=5, pady=8)
            entry = ttk.Entry(body, width=20)
            entry.grid(row=i, column=1, padx=5, pady=8)
            self.entries[field] = entry
        
        if existing_state:
            for i, field in enumerate(fields):
                self.entries[field].insert(0, existing_state[i])
        
        if name_readonly:
            self.entries[fields[0]].config(state="readonly")

        self.entries[fields[0]].focus_set()

        button_box = ttk.Frame(body)
        button_box.grid(row=len(fields), columnspan=2, pady=20)
        ok_text = "Apply Changes" if existing_state else "Add"
        ttk.Button(button_box, text=ok_text, command=self.on_ok, bootstyle=SUCCESS).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_box, text="Cancel", command=self.on_cancel).pack(side=tk.LEFT, padx=5)
        
        if existing_state:
            ttk.Button(button_box, text="Delete", command=self.on_delete, bootstyle=DANGER).pack(side=tk.LEFT, padx=15)

        self.bind("<Return>", self.on_ok)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.wait_window(self)

    def on_ok(self, event=None):
        try:
            state_values = [self.entries[f].get() for f in self.entries]
            name = state_values[0]
            if not name: raise ValueError("Name is required.")
            
            float_values = [float(v) for v in state_values[1:]]
            width, height = float_values[2], float_values[3]
            if width <= 0 or height <= 0: raise ValueError("Width and height must be positive.")

            self.result = tuple([name] + float_values)
            self.destroy()
        except (ValueError, TclError) as e: messagebox.showerror("Input Error", str(e), parent=self)

    def on_delete(self):
        if messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete this item?", parent=self):
            self.result = 'delete'; self.destroy()

    def on_cancel(self): self.result = None; self.destroy()

# --- Specialized Dialogs ---
class RoomDialog(BaseDialog):
    """Dialog for adding or editing a room."""
    def __init__(self, parent, existing_room_state=None):
        title = "Edit Room Properties" if existing_room_state else "Add New Room"
        fields = ["Room Name", "Start X", "Start Y", "Width", "Height"]
        super().__init__(parent, title, fields, existing_room_state)

class ObjectDialog(BaseDialog):
    """Dialog for editing an object."""
    def __init__(self, parent, existing_object_state):
        title = "Edit Object Properties"
        fields = ["Object Name", "Center X", "Center Y", "Width", "Height"]
        super().__init__(parent, title, fields, existing_object_state, name_readonly=False)

# --- Main Application ---
class BlueprintApp(ttk.Window):
    """The main application window, inheriting from ttk.Window for theming."""
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Modelum")
        self.geometry("1400x900")

        self.house, self.furnishings = [], []
        self.selected_item = None
        self.history, self.redo_stack = [], []
        self.clipboard = None
        self.current_action, self.action_start_xy, self.ghost_rect = None, None, None
        self.object_to_add = None
        self.draw_mode_active = tk.BooleanVar(value=False)
        self.original_state = None
        self.resize_handle = None

        self.object_templates = {
            "Bed (Queen)": (5, 6.7), "Dining Table": (6, 3.5),
            "Sofa": (7, 3), "Chair": (2, 2), "Rug": (8, 5)
        }
        
        self.setup_ui()
        self.setup_shortcuts()
        self.draw_blueprint()

    def setup_ui(self):
        self.controls_frame = ttk.Frame(self, padding="15", width=300)
        self.controls_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.controls_frame.pack_propagate(False)

        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self._create_actions_ui()
        self._create_creative_tools_ui()
        self._create_objects_ui()
        self._create_options_ui()

        self.fig = plt.Figure()
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.canvas_frame)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.canvas_frame, pack_toolbar=False)
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('scroll_event', self.on_scroll)
    
    def _create_actions_ui(self):
        frame = ttk.LabelFrame(self.controls_frame, text="Editing Actions", padding="15")
        frame.pack(fill=tk.X, pady=(0, 10))
        
        self.copy_button = self._create_button(frame, "⎘ Copy Room", self.copy_room, "Ctrl+C", (OUTLINE, INFO))
        self.paste_button = self._create_button(frame, "📋 Paste Room", self.paste_room, "Ctrl+V", (OUTLINE, INFO))
        self.update_buttons()
    
    def _create_creative_tools_ui(self):
        frame = ttk.LabelFrame(self.controls_frame, text="Creative Tools", padding="15")
        frame.pack(fill=tk.X, pady=10)
        
        self.draw_room_button = ttk.Checkbutton(frame, text="✏️ Draw Room", variable=self.draw_mode_active,
                                                command=self.toggle_draw_mode, bootstyle="toolbutton-outline")
        self.draw_room_button.pack(fill=tk.X, pady=5)
        ToolTip(self.draw_room_button, "Toggle mode to draw new rooms")

        self._create_button(frame, "＋ Add Room...", self.prompt_add_room_precise, "Enter", (OUTLINE, PRIMARY))
        self._create_button(frame, "🏠 Generate House", self.generate_random_layout, None, SUCCESS)

    def _create_objects_ui(self):
        frame = ttk.LabelFrame(self.controls_frame, text="Place Objects", padding="15")
        frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(frame, text="Object Type:").pack(fill=tk.X, pady=(0, 2))
        self.object_combo = ttk.Combobox(frame, values=list(self.object_templates.keys()), state="readonly")
        self.object_combo.pack(fill=tk.X, pady=(0, 8))
        self.object_combo.set(list(self.object_templates.keys())[0])

        self._create_button(frame, "＋ Add Object", self.enter_add_object_mode, None, INFO)

    def _create_options_ui(self):
        frame = ttk.LabelFrame(self.controls_frame, text="Blueprint Info", padding="15")
        frame.pack(fill=tk.X, pady=10)
        
        self.total_sqft_label = ttk.Label(frame, text="Total Area: 0.00 sqft", font=("Helvetica", 10, "bold"))
        self.total_sqft_label.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))

        self.clear_button = ttk.Button(frame, text="Clear All", command=self.clear_blueprint, bootstyle=(OUTLINE, DANGER))
        self.clear_button.pack(side=tk.TOP, fill=tk.X)

    def _create_button(self, parent, text, command, shortcut, bootstyle):
        btn = ttk.Button(parent, text=text, command=command, bootstyle=bootstyle)
        btn.pack(fill=tk.X, pady=5)
        if shortcut: ToolTip(btn, text=f"Shortcut: {shortcut}")
        return btn

    def setup_shortcuts(self):
        nudge_amount = 0.2
        self.bind("<Control-z>", lambda event: self.undo())
        self.bind("<Control-y>", lambda event: self.redo())
        self.bind("<Control-c>", lambda event: self.copy_room())
        self.bind("<Control-v>", lambda event: self.paste_room())
        self.bind("<Return>", lambda event: self.prompt_add_room_precise())
        self.bind("<Up>", lambda event: self.move_selected(0, nudge_amount))
        self.bind("<Down>", lambda event: self.move_selected(0, -nudge_amount))
        self.bind("<Left>", lambda event: self.move_selected(-nudge_amount, 0))
        self.bind("<Right>", lambda event: self.move_selected(nudge_amount, 0))
        self.bind("<Escape>", lambda event: self.cancel_action())
        self.bind("<Delete>", self.delete_selected_item)

    def log_action(self, action):
        self.history.append(action); self.redo_stack.clear(); self.update_buttons()
    
    def move_selected(self, dx, dy):
        if not self.selected_item: return
        
        item_type = 'room' if isinstance(self.selected_item, Room) else 'obj'
        old_state = self.selected_item.get_state()
        new_state = (old_state[0], old_state[1] + dx, old_state[2] + dy, old_state[3], old_state[4])
        self.selected_item.update_state(new_state)
        self.log_action((f'edit_{item_type}', self.selected_item, old_state, new_state))
        self.draw_blueprint()

    def prompt_add_room_precise(self):
        dialog = RoomDialog(self)
        if isinstance(dialog.result, tuple):
            new_room = Room(*dialog.result)
            self.house.append(new_room)
            self.log_action(('add_room', new_room, new_room.get_state(), None))
            self.draw_blueprint()

    def copy_room(self):
        if isinstance(self.selected_item, Room):
            self.clipboard = self.selected_item.get_state()
            self.update_buttons()

    def paste_room(self):
        if not self.clipboard: return
        name, _, _, width, height = self.clipboard; new_name = f"{name}(copy)"
        x_lim, y_lim = self.ax.get_xlim(), self.ax.get_ylim()
        new_x, new_y = (x_lim[0] + x_lim[1]) / 2, (y_lim[0] + y_lim[1]) / 2
        new_room = Room(new_name, new_x, new_y, width, height)
        self.house.append(new_room)
        self.log_action(('add_room', new_room, new_room.get_state(), None))
        self.select_item(new_room)
        self.draw_blueprint()

    def generate_random_layout(self):
        if self.house and not messagebox.askyesno("Confirm", "This will clear the current layout. Continue?", parent=self):
            return
        self.clear_blueprint(confirm=False)
        templates = {"Living Room":{'w':(15,22),'h':(12,18)}, "Kitchen":{'w':(8,14),'h':(8,14)}, "Master Bedroom":{'w':(12,18),'h':(10,15)}, "Bathroom":{'w':(6,9),'h':(6,9)}}
        lr_w, lr_h = random.uniform(*templates["Living Room"]['w']), random.uniform(*templates["Living Room"]['h'])
        living_room = Room("Living Room", 0, 0, lr_w, lr_h); self.house.append(living_room)
        k_w, k_h = random.uniform(*templates["Kitchen"]['w']), random.uniform(*templates["Kitchen"]['h'])
        self.house.append(Room("Kitchen", lr_w, random.uniform(0, lr_h - k_h), k_w, k_h))
        mbr_w, mbr_h = random.uniform(*templates["Master Bedroom"]['w']), random.uniform(*templates["Master Bedroom"]['h'])
        self.house.append(Room("Master Bedroom", random.uniform(0, lr_w - mbr_w), lr_h, mbr_w, mbr_h))
        b_w, b_h = random.uniform(*templates["Bathroom"]['w']), random.uniform(*templates["Bathroom"]['h'])
        self.house.append(Room("Bathroom", lr_w, self.house[1].y + k_h, b_w, b_h))
        self.update_buttons(); self.draw_blueprint()

    #! MODIFIED: Rewritten to better prioritize moving vs. resizing.
    def on_press(self, event):
        if event.inaxes != self.ax or self.toolbar.mode:
            return
        self.action_start_xy = (event.xdata, event.ydata)

        # Handle placing a new object
        if self.object_to_add:
            self.add_object_at(event.xdata, event.ydata)
            return

        # Handle double-click to edit properties
        if event.dblclick:
            item = self.find_item_at(event.xdata, event.ydata)
            if isinstance(item, Room): self.prompt_edit_room_properties(item)
            elif isinstance(item, BlueprintObject): self.prompt_edit_object_properties(item)
            return

        # Determine user's intent: resize, move, or draw
        item_under_cursor = self.find_item_at(event.xdata, event.ydata)
        resize_handle = None
        if isinstance(item_under_cursor, Room):
            resize_handle = item_under_cursor.get_resize_handle(event.xdata, event.ydata)

        # --- Action Logic ---
        # 1. RESIZE: Only if a resize handle is clicked and the item is already selected.
        #    This makes resizing a more deliberate action.
        if resize_handle and item_under_cursor == self.selected_item:
            self.current_action = 'resizing_room'
            self.resize_handle = resize_handle
            self.original_state = self.selected_item.get_state()
        
        # 2. MOVE or SELECT: If any item is clicked (even on an edge), select and prepare to move it.
        elif item_under_cursor:
            self.select_item(item_under_cursor) # Select the item immediately
            self.current_action = 'moving'
            self.original_state = self.selected_item.get_state()
            
        # 3. DRAW: If the canvas is empty and draw mode is on.
        elif self.draw_mode_active.get():
            self.select_item(None) # Deselect any previously selected item
            self.current_action = 'drawing_room'
            self.ghost_rect = patches.Rectangle(self.action_start_xy, 0, 0, facecolor='#18BC9C', alpha=0.4)
            self.ax.add_patch(self.ghost_rect)
            
        # 4. DESELECT: If clicking on an empty area without draw mode.
        else:
            self.select_item(None)

        self.draw_blueprint()

    def on_motion(self, event):
        if not event.inaxes or self.toolbar.mode: return
        
        # Ghost preview for placing a new object
        if self.object_to_add:
            w, h = self.object_templates[self.object_to_add]
            if not self.ghost_rect:
                self.ghost_rect = patches.Rectangle((0,0), w, h, facecolor='#F39C12', alpha=0.6)
                self.ax.add_patch(self.ghost_rect)
            self.ghost_rect.set_xy((event.xdata - w/2, event.ydata - h/2))
            self.canvas.draw_idle()
            return
        
        # Update cursor based on context if no action is in progress
        if not self.current_action:
            cursor = 'arrow'
            # Check for resize handle only on the currently selected item
            if isinstance(self.selected_item, Room) and self.selected_item.get_resize_handle(event.xdata, event.ydata):
                cursor = 'plus' 
            elif self.find_item_at(event.xdata, event.ydata):
                cursor = 'fleur' # Move cursor
            elif self.draw_mode_active.get():
                cursor = 'crosshair'
            self.canvas.get_tk_widget().config(cursor=cursor)
            return

        # Handle dragging actions (move, resize, draw)
        if not self.action_start_xy: return
        x, y = event.xdata, event.ydata
        sx, sy = self.action_start_xy
        
        if self.current_action == 'drawing_room' and self.ghost_rect:
            self.ghost_rect.set_width(x - sx); self.ghost_rect.set_height(y - sy)
        elif self.current_action == 'moving' and self.selected_item:
            dx, dy = x - sx, y - sy
            os = self.original_state
            self.selected_item.update_state((os[0], os[1] + dx, os[2] + dy, os[3], os[4]))
        elif self.current_action == 'resizing_room' and self.selected_item:
            n, ox, oy, ow, oh = self.original_state
            nx, ny, nw, nh = ox, oy, ow, oh
            # Ensure dimensions don't become negative
            if 'right' in self.resize_handle: nw = max(1, x - ox)
            if 'left' in self.resize_handle: nw, nx = max(1, (ox + ow) - x), x
            if 'top' in self.resize_handle: nh = max(1, y - oy)
            if 'bottom' in self.resize_handle: nh, ny = max(1, (oy + oh) - y), y
            self.selected_item.update_state((n, nx, ny, nw, nh))
        
        self.draw_blueprint()

    def on_release(self, event):
        if not self.current_action: return
        
        item_type = None
        if isinstance(self.selected_item, Room): item_type = 'room'
        elif isinstance(self.selected_item, BlueprintObject): item_type = 'obj'

        if self.current_action == 'drawing_room' and self.ghost_rect:
            w, h = self.ghost_rect.get_width(), self.ghost_rect.get_height()
            if abs(w) > 1 and abs(h) > 1:
                sx, sy = self.action_start_xy
                x_start = min(sx, sx + w)
                y_start = min(sy, sy + h)
                name = simpledialog.askstring("Room Name", "Enter a name:", parent=self)
                if name:
                    nr = Room(name, x_start, y_start, abs(w), abs(h))
                    self.house.append(nr)
                    self.log_action(('add_room', nr, nr.get_state(), None))
            if self.ghost_rect in self.ax.patches:
                self.ghost_rect.remove()
            self.ghost_rect = None

        elif self.current_action in ['moving', 'resizing_room']:
            if self.selected_item and self.selected_item.get_state() != self.original_state:
                self.log_action((f'edit_{item_type}', self.selected_item, self.original_state, self.selected_item.get_state()))

        self.current_action, self.original_state, self.resize_handle = None, None, None
        self.draw_blueprint()

    def on_scroll(self, event):
        if event.inaxes != self.ax: return
        base_scale = 1.1
        cur_xlim, cur_ylim = self.ax.get_xlim(), self.ax.get_ylim()
        scale_factor = 1 / base_scale if event.button == 'up' else base_scale
        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
        relx = (event.xdata - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0])
        rely = (event.ydata - cur_ylim[0]) / (cur_ylim[1] - cur_ylim[0])
        self.ax.set_xlim([event.xdata - new_width * relx, event.xdata + new_width * (1-relx)])
        self.ax.set_ylim([event.ydata - new_height * rely, event.ydata + new_height * (1-rely)])
        self.canvas.draw_idle()

    def find_item_at(self, x, y):
        # Check furnishings first as they are "on top"
        for obj in reversed(self.furnishings):
            if obj.contains(x, y): return obj
        for room in reversed(self.house):
            if room.contains(x, y): return room
        return None

    def prompt_edit_room_properties(self, room):
        old_state = room.get_state()
        dialog = RoomDialog(self, old_state)
        res = dialog.result
        if res == 'delete':
            self.house.remove(room)
            self.log_action(('delete_room', room, old_state, None))
            if self.selected_item == room: self.select_item(None)
        elif isinstance(res, tuple) and res != old_state:
            room.update_state(res)
            self.log_action(('edit_room', room, old_state, res))
        self.draw_blueprint()

    def prompt_edit_object_properties(self, obj):
        old_state = obj.get_state()
        dialog = ObjectDialog(self, old_state)
        res = dialog.result
        if res == 'delete':
            self.furnishings.remove(obj)
            self.log_action(('delete_obj', obj, old_state, None))
            if self.selected_item == obj: self.select_item(None)
        elif isinstance(res, tuple) and res != old_state:
            obj.update_state(res)
            self.log_action(('edit_obj', obj, old_state, res))
        self.draw_blueprint()

    def toggle_draw_mode(self):
        if self.draw_mode_active.get():
            self.cancel_action(clear_draw_mode=False)
        self.canvas.get_tk_widget().config(cursor='crosshair' if self.draw_mode_active.get() else 'arrow')

    def enter_add_object_mode(self):
        self.cancel_action()
        self.object_to_add = self.object_combo.get()
        self.canvas.get_tk_widget().config(cursor='tcross')

    def add_object_at(self, x, y):
        name = self.object_to_add
        w, h = self.object_templates[name]
        new_obj = BlueprintObject(name, x - w/2, y - h/2, w, h)
        self.furnishings.append(new_obj)
        self.log_action(('add_obj', new_obj, new_obj.get_state(), None))
        self.cancel_action()

    def cancel_action(self, clear_draw_mode=True):
        if self.ghost_rect:
            try: self.ghost_rect.remove()
            except (ValueError, AttributeError): pass
            self.ghost_rect = None
        
        self.object_to_add = None
        if clear_draw_mode:
            self.draw_mode_active.set(False)
        
        self.current_action = None
        self.canvas.get_tk_widget().config(cursor='arrow')
        self.draw_blueprint()

    def undo(self):
        if not self.history: return
        action, item, s1, s2 = self.history.pop()
        if action == 'add_room': self.house.remove(item)
        elif action == 'delete_room': self.house.append(item); item.update_state(s1)
        elif action == 'edit_room': item.update_state(s1)
        elif action == 'add_obj': self.furnishings.remove(item)
        elif action == 'delete_obj': self.furnishings.append(item); item.update_state(s1)
        elif action == 'edit_obj': item.update_state(s1)
        self.redo_stack.append((action, item, s1, s2)); self.update_buttons(); self.draw_blueprint()

    def redo(self):
        if not self.redo_stack: return
        action, item, s1, s2 = self.redo_stack.pop()
        if action == 'add_room': self.house.append(item)
        elif action == 'delete_room': self.house.remove(item)
        elif action == 'edit_room': item.update_state(s2)
        elif action == 'add_obj': self.furnishings.append(item)
        elif action == 'delete_obj': self.furnishings.remove(item)
        elif action == 'edit_obj': item.update_state(s2)
        self.history.append((action, item, s1, s2)); self.update_buttons(); self.draw_blueprint()
    
    def clear_blueprint(self, confirm=True):
        if confirm and not messagebox.askyesno("Confirm", "This will clear the layout and all history. Continue?", parent=self):
            return
        self.house.clear(); self.furnishings.clear(); self.history.clear(); self.redo_stack.clear()
        self.select_item(None)
        self.update_buttons()

    def delete_selected_item(self, event=None):
        if not self.selected_item: return
        
        item_name = self.selected_item.name
        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete '{item_name}'?", parent=self):
            return

        item = self.selected_item
        old_state = item.get_state()
        
        if isinstance(item, Room):
            self.house.remove(item)
            self.log_action(('delete_room', item, old_state, None))
        elif isinstance(item, BlueprintObject):
            self.furnishings.remove(item)
            self.log_action(('delete_obj', item, old_state, None))
        
        self.select_item(None)

    def select_item(self, item):
        if self.selected_item != item:
            self.selected_item = item
            self.update_buttons()
            self.draw_blueprint() # Redraw on selection change

    def update_buttons(self):
        is_room_selected = isinstance(self.selected_item, Room)
        self.copy_button.config(state=NORMAL if is_room_selected else DISABLED)
        self.paste_button.config(state=NORMAL if self.clipboard else DISABLED)

    def format_text_for_room(self, name, width):
        avg_char_width = 0.6 
        chars_per_line = max(1, int(width / avg_char_width))
        wrapper = textwrap.TextWrapper(width=chars_per_line, break_long_words=True, break_on_hyphens=False)
        wrapped_lines = wrapper.wrap(text=name)
        return '\n'.join(wrapped_lines)

    def draw_blueprint(self):
        xlim_before, ylim_before = self.ax.get_xlim(), self.ax.get_ylim()
        self.ax.clear()
        
        palette = {
            'bg': '#2B3E50', 'text': '#EAEAEA', 'grid': '#4E6A85', 
            'room_face': '#34495E', 'room_edge': '#9CC2E5', 'selected_edge': '#18BC9C',
            'obj_face': '#8E44AD', 'obj_edge': '#BD93D8', 'selected_obj_edge': '#F39C12',
        }
        
        self.fig.patch.set_facecolor(palette['bg'])
        self.ax.set_facecolor(palette['bg'])
        self.ax.tick_params(colors=palette['text'], which='both')
        for spine in self.ax.spines.values(): spine.set_edgecolor(palette['grid'])
        
        self.ax.set_title("Modelum", color=palette['text'], weight='bold', fontsize=16)
        self.ax.set_xlabel("Width (feet)", color=palette['text'])
        self.ax.set_ylabel("Height (feet)", color=palette['text'])
        
        total_sqft = 0
        for r in self.house:
            w, h = max(0.1, r.width), max(0.1, r.height)
            area = w * h; total_sqft += area
            ec, lw = (palette['selected_edge'], 2.5) if r == self.selected_item else (palette['room_edge'], 1.5)
            p = patches.Rectangle((r.x, r.y), w, h, edgecolor=ec, facecolor=palette['room_face'], linewidth=lw, zorder=2)
            self.ax.add_patch(p)
            
            wrapped_name = self.format_text_for_room(r.name, w)
            full_text = f"{wrapped_name}\n({area:.2f} sqft)"
            self.ax.text(r.x + w / 2, r.y + h / 2, full_text, 
                         ha='center', va='center', fontsize=8, color=palette['text'], wrap=True, zorder=5)
        
        for obj in self.furnishings:
            w, h = max(0.1, obj.width), max(0.1, obj.height)
            ec, lw = (palette['selected_obj_edge'], 2.0) if obj == self.selected_item else (palette['obj_edge'], 1.0)
            p = patches.Rectangle((obj.x, obj.y), w, h, edgecolor=ec, facecolor=palette['obj_face'], linewidth=lw, zorder=4)
            self.ax.add_patch(p)
            self.ax.text(obj.x + w / 2, obj.y + h / 2, obj.name,
                         ha='center', va='center', fontsize=6, color=palette['text'], wrap=True, zorder=5)

        self.total_sqft_label.config(text=f"Total Area: {total_sqft:.2f} sqft")

        if self.ghost_rect and self.ghost_rect not in self.ax.patches:
            self.ax.add_patch(self.ghost_rect)
        
        is_first_draw = xlim_before == (0.0, 1.0) and ylim_before == (0.0, 1.0)
        if self.house or self.furnishings:
            all_items = self.house + self.furnishings
            all_x = [item.x for item in all_items] + [item.x + item.width for item in all_items]
            all_y = [item.y for item in all_items] + [item.y + item.height for item in all_items]
            if is_first_draw and all_x and all_y:
                min_x, max_x = min(all_x), max(all_x)
                min_y, max_y = min(all_y), max(all_y)
                x_margin = max(5, (max_x - min_x) * 0.1)
                y_margin = max(5, (max_y - min_y) * 0.1)
                self.ax.set_xlim(min_x - x_margin, max_x + x_margin)
                self.ax.set_ylim(min_y - y_margin, max_y + y_margin)
            else:
                self.ax.set_xlim(xlim_before); self.ax.set_ylim(ylim_before)
        elif is_first_draw:
            self.ax.set_xlim(0, 50); self.ax.set_ylim(0, 50)
        else:
            self.ax.set_xlim(xlim_before); self.ax.set_ylim(ylim_before)
        
        self.ax.set_aspect('equal', adjustable='box')
        self.ax.grid(True, linestyle='--', color=palette['grid'], alpha=0.6, zorder=0)
        self.canvas.draw_idle()

# --- Helper class for Tooltips ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget; self.text = text
        self.widget.bind("<Enter>", self.enter); self.widget.bind("<Leave>", self.leave)
        self.toplevel = None

    def enter(self, event=None):
        if self.toplevel: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.toplevel = tk.Toplevel(self.widget)
        self.toplevel.wm_overrideredirect(True)
        self.toplevel.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.toplevel, text=self.text, bootstyle=INVERSE)
        label.pack(ipadx=5, ipady=5)

    def leave(self, event=None):
        if self.toplevel:
            self.toplevel.destroy()
            self.toplevel = None

if __name__ == "__main__":
    app = BlueprintApp()
    app.mainloop()
