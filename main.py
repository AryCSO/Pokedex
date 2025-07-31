import customtkinter as ctk
import requests
import threading
from PIL import Image, ImageSequence, UnidentifiedImageError
from io import BytesIO
from functools import partial
import pystray
import sys
from pynput import keyboard

TYPE_COLORS = {
    "normal": "#A8A77A", "fire": "#EE8130", "water": "#6390F0", "electric": "#F7D02C",
    "grass": "#7AC74C", "ice": "#96D9D6", "fighting": "#C22E28", "poison": "#A33EA1",
    "ground": "#E2BF65", "flying": "#A98FF3", "psychic": "#F95587", "bug": "#A6B91A",
    "rock": "#B6A136", "ghost": "#735797", "dragon": "#6F35FC", "dark": "#705746",
    "steel": "#B7B7CE", "fairy": "#D685AD"
}

STAT_TRANSLATIONS = {
    "hp": "HP", "attack": "Ataque", "defense": "Defesa",
    "special-attack": "Ataque Sp.", "special-defense": "Defesa Sp.", "speed": "Velocidade"
}

TYPE_TRANSLATIONS = {
    "normal": "Normal", "fire": "Fogo", "water": "Água", "electric": "Elétrico",
    "grass": "Planta", "ice": "Gelo", "fighting": "Lutador", "poison": "Veneno",
    "ground": "Terra", "flying": "Voador", "psychic": "Psíquico", "bug": "Inseto",
    "rock": "Pedra", "ghost": "Fantasma", "dragon": "Dragão", "dark": "Sombrio",
    "steel": "Aço", "fairy": "Fada"
}

class PokedexApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Pokedex")
        try:
            self.iconbitmap('poke.ico')
        except Exception as e:
            print(f"Não foi possível carregar o ícone 'poke.ico': {e}")
        
        window_width = 1280
        window_height = 720
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        self.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
        
        self.minsize(800, 600)
        self.resizable(True, True)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.font_family = "Oswald"
        self.update_font_sizes()

        self.current_search_id = 0
        self.pokemon_image = None 
        self.animation_frames = []
        self.all_pokemon_list = []
        self.navigation_history = []
        self.history_index = -1
        self.grid_cards = []
        self.focused_card_index = None
        self.current_pokedex_id = None
        self.current_pokemon_data = None
        self.show_shiny = False
        self.blank_image = ctk.CTkImage(light_image=Image.new("RGBA", (1, 1), (0,0,0,0)), size=(1,1))
        self.api_cache = {}
        self.image_cache = {}
        self.hotkey_listener = None
        
        self.create_widgets()
        
        self.bind("<Escape>", self.handle_escape)
        self.bind("<Left>", self.prev_pokemon_event)
        self.bind("<Right>", self.next_pokemon_event)
        self.bind("<BackSpace>", self.handle_backspace_nav)
        
        self._resize_job = None
        self.bind('<Configure>', self._on_resize_debounce)
        
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.tray_thread = threading.Thread(target=self.setup_tray_icon, daemon=True)
        self.tray_thread.start()
        self.hotkey_thread = threading.Thread(target=self.setup_hotkey_listener, daemon=True)
        self.hotkey_thread.start()
        
        threading.Thread(target=self.load_all_pokemon_names, daemon=True).start()

    def create_widgets(self):
        """Cria todos os widgets da interface."""
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(pady=10, padx=20, fill="x")

        self.back_button = ctk.CTkButton(top_frame, text="←", height=40, width=40, font=self.font_icon, command=self.go_back, state="disabled", fg_color="#B71C1C", hover_color="#D32F2F")
        self.back_button.pack(side="left", padx=(0,5))

        self.forward_button = ctk.CTkButton(top_frame, text="→", height=40, width=40, font=self.font_icon, command=self.go_forward, state="disabled", fg_color="#B71C1C", hover_color="#D32F2F")
        self.forward_button.pack(side="left", padx=(0,10))

        self.search_entry = ctk.CTkEntry(top_frame, placeholder_text="Digite o nome ou número do Pokémon...", height=40, font=self.font_body)
        self.search_entry.pack(side="left", expand=True, fill="x", padx=(0, 10))
        self.search_entry.bind("<Return>", self.search_pokemon_event)

        search_icon = "🔍"
        self.search_button = ctk.CTkButton(top_frame, text=search_icon, height=40, width=40, command=self.search_pokemon_event, font=self.font_icon, fg_color="#B71C1C", hover_color="#D32F2F")
        self.search_button.pack(side="left", padx=10)
        
        home_icon = "⌂" 
        self.home_button = ctk.CTkButton(top_frame, text=home_icon, height=40, width=40, font=self.font_icon, command=self.refresh_app, fg_color="#B71C1C", hover_color="#D32F2F")
        self.home_button.pack(side="left", padx=(0,10))

        self.theme_switch = ctk.CTkSwitch(top_frame, text="Tema Escuro", command=self.toggle_theme, progress_color="#E53935", font=self.font_small)
        self.theme_switch.pack(side="left", padx=(10, 0))
        self.theme_switch.select()

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=10)

        self.home_page = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.home_page.pack(fill="both", expand=True)

        try:
            self.pokeball_image_pil = Image.open("Group 23.png")
            self.home_image_label = ctk.CTkLabel(self.home_page, text="")
            self.home_image_label.place(relx=0.5, rely=0.5, anchor="center")
        except FileNotFoundError:
            self.pokeball_image_pil = None
            self.home_image_label = ctk.CTkLabel(self.home_page, text="Pokedex")
            self.home_image_label.place(relx=0.5, rely=0.5, anchor="center")

        self.search_results_page = ctk.CTkScrollableFrame(self.main_container, fg_color=("gray92", "gray17"))
        self.search_results_grid = ctk.CTkFrame(self.search_results_page, fg_color="transparent")
        self.search_results_grid.pack(fill="both", expand=True)

        self.detail_page = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self._create_detail_view_widgets()

        self.loading_frame = ctk.CTkFrame(self, fg_color=("#ffffff", "#1a1a1a"))
        self.loading_progressbar = ctk.CTkProgressBar(self.loading_frame, mode="indeterminate", progress_color="#E53935")
        self.loading_progressbar.place(relx=0.5, rely=0.5, anchor="center")
        self.loading_label = ctk.CTkLabel(self.loading_frame, text="A carregar...")
        self.loading_label.place(relx=0.5, rely=0.5, anchor="s", y=-10)
        
        self.after(100, self.update_responsive_layout)

    def _create_detail_view_widgets(self):
        """Cria os widgets da tela de detalhes."""
        self.detail_page.grid_columnconfigure(0, weight=1, minsize=60)
        self.detail_page.grid_columnconfigure(1, weight=8)
        self.detail_page.grid_columnconfigure(2, weight=1, minsize=60)
        self.detail_page.grid_rowconfigure(0, weight=1)

        self.prev_pokemon_button = ctk.CTkButton(self.detail_page, text="◄", width=50, fg_color="transparent", hover_color="gray20", command=self.prev_pokemon_event)
        self.prev_pokemon_button.grid(row=0, column=0, sticky="nsw")

        content_container = ctk.CTkFrame(self.detail_page, fg_color="transparent")
        content_container.grid(row=0, column=1, sticky="nsew")
        content_container.grid_columnconfigure(0, weight=4)
        content_container.grid_columnconfigure(1, weight=6)
        content_container.grid_rowconfigure(0, weight=1)

        self.next_pokemon_button = ctk.CTkButton(self.detail_page, text="►", width=50, fg_color="transparent", hover_color="gray20", command=self.next_pokemon_event)
        self.next_pokemon_button.grid(row=0, column=2, sticky="nse")

        left_frame = ctk.CTkFrame(content_container, fg_color=("gray88", "gray14"), corner_radius=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        self.image_placeholder = ctk.CTkFrame(left_frame, fg_color="transparent")
        self.image_placeholder.grid(row=0, column=0, sticky="nsew", padx=30, pady=30)
        self.image_label = ctk.CTkLabel(self.image_placeholder, text="", image=self.blank_image, fg_color="transparent")
        self.image_label.pack(expand=True)
        
        name_shiny_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        name_shiny_frame.grid(row=1, column=0, sticky="n", padx=20, pady=(0, 10))
        
        self.name_label = ctk.CTkLabel(name_shiny_frame, text="", wraplength=400)
        self.name_label.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        self.shiny_button = ctk.CTkButton(name_shiny_frame, text="✨", command=self.toggle_shiny, fg_color=("gray70", "gray25"), hover_color=("gray60", "gray35"), width=40, height=40)
        self.shiny_button.pack(side="left")

        self.pokedex_entry_label = ctk.CTkLabel(left_frame, text="", wraplength=400, justify="center")
        self.pokedex_entry_label.grid(row=2, column=0, sticky="n", padx=20, pady=(0, 10))
        
        self.evolution_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        self.evolution_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 20))

        right_frame = ctk.CTkFrame(content_container, fg_color=("gray88", "gray14"), corner_radius=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        stats_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        stats_frame.pack(pady=10, padx=30, fill="x")
        stats_frame.columnconfigure(1, weight=1)
        stats_frame.columnconfigure(2, weight=0)

        self.stat_labels, self.stat_bars, self.stat_values = {}, {}, {}
        self.stats_to_display = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
        
        for i, stat in enumerate(self.stats_to_display):
            display_name = STAT_TRANSLATIONS.get(stat, stat.replace('-', ' ').title())
            label = ctk.CTkLabel(stats_frame, text=f"{display_name}:", anchor="w")
            label.grid(row=i, column=0, sticky="w", padx=10, pady=4)
            
            bar = ctk.CTkProgressBar(stats_frame, orientation="horizontal", height=15, corner_radius=8, progress_color="#E53935")
            bar.grid(row=i, column=1, sticky="ew", padx=10, pady=4)
            
            value_label = ctk.CTkLabel(stats_frame, text="", width=35, anchor="e")
            value_label.grid(row=i, column=2, sticky="e", padx=(5, 0), pady=4)
            
            self.stat_labels[stat], self.stat_bars[stat], self.stat_values[stat] = label, bar, value_label

        self.types_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        self.types_frame.pack(pady=10, padx=20)
        self.type1_label = ctk.CTkLabel(self.types_frame, text="", corner_radius=8, width=100, height=35)
        self.type2_label = ctk.CTkLabel(self.types_frame, text="", corner_radius=8, width=100, height=35)
        
        self.locations_frame = ctk.CTkScrollableFrame(right_frame, label_text="Localização")
        self.locations_frame.pack(pady=10, padx=20, fill="both", expand=True)

    def setup_tray_icon(self):
        try:
            image = Image.open("poke.ico")
        except FileNotFoundError:
            image = Image.new('RGB', (64, 64), color = 'black')
        menu = (pystray.MenuItem('Mostrar Pokedex', self.show_window, default=True), pystray.MenuItem('Sair', self.quit_app))
        self.tray_icon = pystray.Icon("pokedex", image, "Pokedex Luxo", menu)
        self.tray_icon.run()

    def hide_window(self):
        self.withdraw()

    def show_window(self, icon=None, item=None):
        self.deiconify()
        self.attributes('-topmost', 1) # Traz a janela para a frente
        self.after(100, lambda: self.attributes('-topmost', 0)) # Permite que outras janelas fiquem por cima depois

    def quit_app(self, icon=None, item=None):
        if self.hotkey_listener and self.hotkey_listener.is_alive():
            self.hotkey_listener.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        self.quit()
        sys.exit()

    def setup_hotkey_listener(self):
        """Configura e inicia o ouvinte de atalho global."""
        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse('<alt>+<shift>+p'),
            self.on_hotkey_activate)
        
        self.hotkey_listener = keyboard.GlobalHotKeys({
            '<alt>+<shift>+p': self.on_hotkey_activate
        })
        self.hotkey_listener.start()

    def on_hotkey_activate(self):
        """Função chamada quando o atalho é pressionado."""
        self.after(0, self.show_window)

    def show_loading_screen(self):
        """Mostra a tela de carregamento sobre todo o conteúdo."""
        self.loading_label.configure(font=self.font_subtitle)
        self.loading_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.loading_frame.tkraise()
        self.loading_progressbar.start()

    def hide_loading_screen(self):
        """Esconde a tela de carregamento."""
        self.loading_progressbar.stop()
        self.loading_frame.place_forget()

    def update_font_sizes(self):
        """Calcula e define os tamanhos de fonte com base no tamanho da janela."""
        height = self.winfo_height()
        scale_factor = max(0.5, height / 720)
        
        self.font_title = ctk.CTkFont(family="Oswald", size=int(32 * scale_factor), weight="bold")
        self.font_subtitle = ctk.CTkFont(family="Oswald", size=int(22 * scale_factor), weight="bold")
        self.font_body = ctk.CTkFont(family="Oswald", size=int(16 * scale_factor))
        self.font_button = ctk.CTkFont(family="Oswald", size=int(14 * scale_factor), weight="bold")
        self.font_small = ctk.CTkFont(family="Oswald", size=int(12 * scale_factor))
        self.font_icon = ctk.CTkFont(size=int(20 * scale_factor))

    def _on_resize_debounce(self, event):
        """Atrasa a chamada de redimensionamento para evitar sobrecarga."""
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(50, self.update_responsive_layout)

    def update_responsive_layout(self):
        """Função principal que ajusta a UI com base no tamanho da janela."""
        self.update_font_sizes()
        width = self.winfo_width()
        height = self.winfo_height()
        
        self.back_button.configure(font=self.font_icon)
        self.forward_button.configure(font=self.font_icon)
        self.search_entry.configure(font=self.font_body)
        self.search_button.configure(font=self.font_icon)
        self.home_button.configure(font=self.font_icon)
        self.theme_switch.configure(font=self.font_small)
        self.name_label.configure(font=self.font_title)
        self.pokedex_entry_label.configure(font=self.font_body)
        self.shiny_button.configure(font=self.font_icon)
        self.type1_label.configure(font=self.font_body)
        self.type2_label.configure(font=self.font_body)
        self.locations_frame.configure(label_font=self.font_button)
        for stat, label in self.stat_labels.items():
            display_name = STAT_TRANSLATIONS.get(stat, stat.replace('-', ' ').title())
            label.configure(font=self.font_body, text=f"{display_name}:")
        for value_label in self.stat_values.values():
            value_label.configure(font=self.font_body)

        if self.home_page.winfo_ismapped() and self.pokeball_image_pil:
            img_size = int(min(width, height) * 0.35)
            pokeball_image = ctk.CTkImage(light_image=self.pokeball_image_pil, size=(img_size, img_size))
            self.home_image_label.configure(image=pokeball_image)
        elif self.home_page.winfo_ismapped():
             self.home_image_label.configure(font=ctk.CTkFont(family="Oswald", size=int(50 * (height / 720)), weight="bold"))

        if self.search_results_page.winfo_ismapped():
            self.redraw_search_grid()

    def redraw_search_grid(self):
        """Redesenha a grade de resultados com um número de colunas adaptativo."""
        grid_width = self.search_results_grid.winfo_width()
        card_min_width = 150
        cols = max(2, grid_width // card_min_width)
        
        all_cards = self.search_results_grid.winfo_children()
        for i, card in enumerate(all_cards):
            row, col = divmod(i, cols)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

    def load_all_pokemon_names(self):
        try:
            response = requests.get("https://pokeapi.co/api/v2/pokemon?limit=1302", timeout=15)
            response.raise_for_status()
            results = response.json()['results']
            self.all_pokemon_list = results
            print("Catálogo de Pokémon (com todas as formas) carregado.")
        except requests.RequestException as e:
            print(f"Erro ao carregar catálogo: {e}")
    
    def add_to_history(self, state):
        if self.history_index < len(self.navigation_history) - 1:
            self.navigation_history = self.navigation_history[:self.history_index + 1]
        self.navigation_history.append(state)
        self.history_index += 1
        self.update_navigation_buttons_state()

    def search_pokemon_event(self, event=None):
        search_term = self.search_entry.get().strip().lower()
        if not search_term: return
        state = {'type': 'search', 'term': search_term}
        self.add_to_history(state)
        self.execute_search(search_term)

    def execute_search(self, search_term):
        if not self.all_pokemon_list:
            self.after(1000, self.execute_search, search_term)
            return

        matches = [p for p in self.all_pokemon_list if search_term in p['name']]
        if search_term.isdigit():
            matches = [p for p in self.all_pokemon_list if p['url'].split('/')[-2] == search_term]

        self.current_search_id += 1
        
        if len(matches) == 1:
            self.show_loading_screen()
            threading.Thread(target=self.perform_detailed_search, args=(matches[0]['name'], self.current_search_id), daemon=True).start()
        elif len(matches) > 1:
            self.display_search_results(matches)
        else:
            self.show_detail_page()
            self.reset_ui_for_search()
            self.name_label.configure(text="Nenhum Pokémon encontrado.")
            self.image_label.configure(image=self.blank_image, text="?")

    def display_search_results(self, matches):
        self.show_search_results_page()
        for widget in self.search_results_grid.winfo_children():
            widget.destroy()

        self.grid_cards = []
        grid_width = self.search_results_page.winfo_width()
        card_min_width = 150
        cols = max(2, grid_width // card_min_width)
        
        for i, pokemon in enumerate(matches):
            self.after(i * 20, self.create_result_card, i, pokemon, cols)
        
        self.after(len(matches) * 20, self.setup_grid_nav)

    def create_result_card(self, i, pokemon, cols):
        """Cria um único card de resultado para a animação."""
        row, col = divmod(i, cols)
        if col == 0: self.grid_cards.append([])
        
        poke_id = pokemon['url'].split('/')[-2]
        display_name = pokemon['name'].replace('-', ' ').title()
        card = ctk.CTkButton(
            self.search_results_grid, text=f"#{poke_id}\n{display_name}", 
            image=self.blank_image, compound="top", font=self.font_small,
            fg_color="gray20", hover_color="#D32F2F", border_width=2, border_color="gray20",
            command=partial(self.on_result_card_click, pokemon['name'])
        )
        card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        self.grid_cards[row].append(card)
        
        sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke_id}.png"
        threading.Thread(target=self._fetch_sprite_for_grid, args=(sprite_url, card), daemon=True).start()

    def setup_grid_nav(self):
        """Configura a navegação por teclado após a animação da grade."""
        self.focused_card_index = (0, 0)
        self.set_grid_focus()
        self.search_results_page.bind("<Up>", self.handle_key_nav)
        self.search_results_page.bind("<Down>", self.handle_key_nav)
        self.search_results_page.bind("<Left>", self.handle_key_nav)
        self.search_results_page.bind("<Right>", self.handle_key_nav)
        self.search_results_page.bind("<Return>", self.handle_key_select)
        self.search_results_page.focus_set()

    def set_grid_focus(self, old_index=None):
        if old_index:
            self.grid_cards[old_index[0]][old_index[1]].configure(border_color="gray20")
        if self.focused_card_index:
            self.grid_cards[self.focused_card_index[0]][self.focused_card_index[1]].configure(border_color="#E53935")

    def handle_key_nav(self, event):
        if not self.focused_card_index or not self.search_results_page.winfo_ismapped(): return
        old_index, (row, col) = self.focused_card_index, self.focused_card_index
        if event.keysym == "Up": row = max(0, row - 1)
        elif event.keysym == "Down": row = min(len(self.grid_cards) - 1, row + 1)
        elif event.keysym == "Left": col = max(0, col - 1)
        elif event.keysym == "Right": col = min(len(self.grid_cards[row]) - 1, col + 1)
        col = min(col, len(self.grid_cards[row]) - 1)
        self.focused_card_index = (row, col)
        self.set_grid_focus(old_index)

    def handle_key_select(self, event):
        if not self.focused_card_index or not self.search_results_page.winfo_ismapped(): return
        self.grid_cards[self.focused_card_index[0]][self.focused_card_index[1]].invoke()

    def handle_backspace_nav(self, event=None):
        if self.focus_get() != self.search_entry:
            self.search_entry.focus_set()
            self.search_entry.icursor(ctk.END)
            return "break"

    def _fetch_sprite_for_grid(self, url, card):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            pil_image = Image.open(BytesIO(response.content))
            ctk_image = ctk.CTkImage(light_image=pil_image, size=(96, 96))
            self.after(0, lambda: card.configure(image=ctk_image))
        except (requests.RequestException, UnidentifiedImageError) as e:
            print(f"Não foi possível carregar o sprite de {url}: {e}")

    def on_result_card_click(self, pokemon_name):
        state = {'type': 'detail', 'name': pokemon_name}
        self.add_to_history(state)
        self.current_search_id += 1
        self.show_loading_screen()
        threading.Thread(target=self.perform_detailed_search, args=(pokemon_name, self.current_search_id), daemon=True).start()

    def perform_detailed_search(self, pokemon_name, search_id):
        if search_id != self.current_search_id: return
        
        if pokemon_name in self.api_cache:
            cached_data = self.api_cache[pokemon_name]
            cached_data['search_id'] = search_id
            self.after(0, self.handle_search_result, cached_data)
            return

        result = {'search_id': search_id, 'status': None, 'data': None, 'locations': None, 'flavor_text': None, 'pt_name': None, 'evolution_chain': None}
        try:
            pokemon_url = f"https://pokeapi.co/api/v2/pokemon/{pokemon_name}"
            response = requests.get(pokemon_url, timeout=10)
            response.raise_for_status()
            pokemon_data = response.json()
            result['data'] = pokemon_data
            
            species_url = pokemon_data['species']['url']
            species_response = requests.get(species_url, timeout=10)
            species_response.raise_for_status()
            species_data = species_response.json()
            result['flavor_text'] = self.parse_flavor_text(species_data)
            result['pt_name'] = self.parse_pokemon_name(species_data, pokemon_name)

            evolution_url = species_data['evolution_chain']['url']
            evolution_response = requests.get(evolution_url, timeout=10)
            evolution_response.raise_for_status()
            result['evolution_chain'] = self.parse_evolution_chain(evolution_response.json()['chain'])

            encounters_url = pokemon_data['location_area_encounters']
            encounter_response = requests.get(encounters_url, timeout=10)
            encounter_response.raise_for_status()
            result['locations'] = self.parse_encounter_data(encounter_response.json())
            
            result['status'] = 'success'
            self.api_cache[pokemon_name] = result.copy()
        except requests.exceptions.RequestException:
            result['status'] = 'error'
        
        self.after(0, self.handle_search_result, result)

    def parse_evolution_chain(self, chain_data):
        """Processa recursivamente os dados da cadeia evolutiva."""
        chain = []
        current = chain_data
        while current:
            species_name = current['species']['name']
            species_id = current['species']['url'].split('/')[-2]
            chain.append({'name': species_name, 'id': species_id})
            if current['evolves_to']:
                current = current['evolves_to'][0]
            else:
                current = None
        return chain

    def parse_pokemon_name(self, species_data, fallback_name):
        """Extrai o nome em PT-BR, com fallback para o nome original."""
        for name_info in species_data.get('names', []):
            if name_info.get('language', {}).get('name') == 'pt':
                return name_info['name']
        return fallback_name.replace('-', ' ').title()

    def parse_flavor_text(self, species_data):
        """Extrai a descrição da Pokédex, priorizando PT e usando EN como fallback."""
        pt_text = None
        en_text = None
        for entry in species_data.get('flavor_text_entries', []):
            lang_name = entry.get('language', {}).get('name')
            if lang_name == 'pt':
                pt_text = entry['flavor_text'].replace('\n', ' ').replace('\f', ' ')
                break
            elif lang_name == 'en' and en_text is None:
                en_text = entry['flavor_text'].replace('\n', ' ').replace('\f', ' ')
        return pt_text or en_text or "Nenhuma descrição disponível."

    def parse_encounter_data(self, encounter_data):
        """Processa os dados de encontro para agrupar por versão de jogo."""
        locations_by_version = {}
        if not encounter_data: return {}
        
        for encounter in encounter_data:
            location_name = encounter['location_area']['name'].replace('-', ' ').replace('route', 'rota').title()
            for version_details in encounter['version_details']:
                version_name = version_details['version']['name'].replace('-', ' ').title()
                if version_name not in locations_by_version:
                    locations_by_version[version_name] = set()
                locations_by_version[version_name].add(location_name)
        
        for version_name in locations_by_version:
            locations_by_version[version_name] = sorted(list(locations_by_version[version_name]))
            
        return locations_by_version

    def handle_search_result(self, result):
        if result['search_id'] != self.current_search_id: 
            self.hide_loading_screen()
            return
            
        self.show_detail_page()
        self.reset_ui_for_search()
        
        if result['status'] == 'success':
            self.display_pokemon_info(result['data'], result['locations'], result['flavor_text'], result['pt_name'], result['evolution_chain'])
        else:
            self.name_label.configure(text="Erro ao buscar detalhes.")
            self.image_label.configure(image=self.blank_image, text="!")
            self.hide_loading_screen()

    def display_pokemon_info(self, data, locations, flavor_text, pt_name, evolution_chain):
        """Preenche a página de detalhes com todas as informações do Pokémon."""
        self.current_pokemon_data = data
        self.show_shiny = False
        self.update_shiny_button_color()

        pokedex_id = data['id']
        self.current_pokedex_id = pokedex_id
        self.update_pokedex_nav_buttons_state()
        types = [t['type']['name'] for t in data['types']]
        
        self.name_label.configure(text=f"{pt_name} #{pokedex_id}")
        self.pokedex_entry_label.configure(text=flavor_text)
        
        self.update_pokemon_image()
        
        type1_name_en = types[0]
        type1_name_pt = TYPE_TRANSLATIONS.get(type1_name_en, type1_name_en.title())
        self.type1_label.configure(text=type1_name_pt, fg_color=TYPE_COLORS.get(type1_name_en, "#FFF"), text_color=self.get_text_color(TYPE_COLORS.get(type1_name_en, "#FFF")))
        self.type1_label.pack(side="left", padx=5)
        
        if len(types) > 1:
            self.type2_label.pack(side="left", padx=5)
            type2_name_en = types[1]
            type2_name_pt = TYPE_TRANSLATIONS.get(type2_name_en, type2_name_en.title())
            self.type2_label.configure(text=type2_name_pt, fg_color=TYPE_COLORS.get(type2_name_en, "#FFF"), text_color=self.get_text_color(TYPE_COLORS.get(type2_name_en, "#FFF")))
        
        api_stats = {s['stat']['name']: s['base_stat'] for s in data['stats']}
        for stat_en in self.stats_to_display:
            value = api_stats.get(stat_en, 0)
            self.stat_bars[stat_en].set(value / 255)
            self.stat_values[stat_en].configure(text=str(value))
            
        for widget in self.locations_frame.winfo_children():
            widget.destroy()
            
        if not locations:
            no_loc_label = ctk.CTkLabel(self.locations_frame, text="Não encontrado em locais selvagens.", font=self.font_body, text_color="gray50")
            no_loc_label.pack(pady=10)
        else:
            for version, areas in sorted(locations.items()):
                version_label = ctk.CTkLabel(self.locations_frame, text=f"Pokémon {version}:", font=self.font_button, anchor="w")
                version_label.pack(fill="x", padx=5, pady=(8, 2))
                for area in areas:
                    area_label = ctk.CTkLabel(self.locations_frame, text=f"  • {area}", font=self.font_small, anchor="w")
                    area_label.pack(fill="x", padx=10)

        for widget in self.evolution_frame.winfo_children():
            widget.destroy()
        
        if len(evolution_chain) > 1:
            for i, pokemon in enumerate(evolution_chain):
                evo_card = ctk.CTkButton(
                    self.evolution_frame, text=pokemon['name'].replace('-', ' ').title(),
                    image=self.blank_image, compound="top", font=self.font_small,
                    fg_color="transparent", hover_color="gray25",
                    command=partial(self.on_result_card_click, pokemon['name'])
                )
                evo_card.pack(side="left", padx=5, expand=True)
                sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon['id']}.png"
                threading.Thread(target=self._fetch_sprite_for_grid, args=(sprite_url, evo_card), daemon=True).start()

                if i < len(evolution_chain) - 1:
                    arrow_label = ctk.CTkLabel(self.evolution_frame, text="→", font=self.font_subtitle)
                    arrow_label.pack(side="left", padx=5)
        else:
            no_evo_label = ctk.CTkLabel(self.evolution_frame, text="Não possui evoluções", font=self.font_small, text_color="gray50")
            no_evo_label.pack()

    def go_back(self):
        if self.history_index > 0:
            self.history_index -= 1
            self.load_state_from_history()
    
    def go_forward(self):
        if self.history_index < len(self.navigation_history) - 1:
            self.history_index += 1
            self.load_state_from_history()

    def load_state_from_history(self):
        state = self.navigation_history[self.history_index]
        display_term = state.get('term', state.get('name', '')).replace('-', ' ')
        self.search_entry.delete(0, 'end')
        self.search_entry.insert(0, display_term)
        if state['type'] == 'search': self.execute_search(state['term'])
        elif state['type'] == 'detail':
            self.current_search_id += 1
            self.show_loading_screen()
            threading.Thread(target=self.perform_detailed_search, args=(state['name'], self.current_search_id), daemon=True).start()
        self.update_navigation_buttons_state()

    def update_navigation_buttons_state(self):
        self.back_button.configure(state="normal" if self.history_index > 0 else "disabled")
        self.forward_button.configure(state="normal" if self.history_index < len(self.navigation_history) - 1 else "disabled")

    def update_pokemon_image(self):
        """Busca a imagem apropriada (normal ou shiny) para o Pokémon atual."""
        if not self.current_pokemon_data: return

        self.current_search_id += 1
        self.image_label.configure(image=self.blank_image, text="")

        sprites = self.current_pokemon_data.get('sprites', {})
        sources_to_try = []
        
        artwork_key = 'front_shiny' if self.show_shiny else 'front_default'
        gif_key = 'front_shiny' if self.show_shiny else 'front_default'
        sprite_key = 'front_shiny' if self.show_shiny else 'front_default'

        try:
            if url := sprites['versions']['generation-v']['black-white']['animated'][gif_key]:
                sources_to_try.append({'type': 'gif', 'url': url})
        except (KeyError, TypeError): pass
        try:
            if url := sprites['other']['official-artwork'][artwork_key]:
                sources_to_try.append({'type': 'artwork', 'url': url})
        except (KeyError, TypeError): pass
        if url := sprites.get(sprite_key):
            sources_to_try.append({'type': 'sprite', 'url': url})

        if sources_to_try:
            self.fetch_image_with_fallback(sources_to_try, self.current_search_id)
        else:
            self.image_label.configure(image=self.blank_image, text="Imagem\nnão disponível")

    def fetch_image_with_fallback(self, sources, search_id):
        if search_id != self.current_search_id: return
        self._try_next_image_source(sources, 0, search_id)

    def _try_next_image_source(self, sources, index, search_id):
        if search_id != self.current_search_id: return
        if index < len(sources):
            source = sources[index]
            threading.Thread(target=self._download_image_thread, args=(source, sources, index, search_id), daemon=True).start()
        else: 
            self.after(0, self._handle_image_error, search_id)

    def _download_image_thread(self, source, all_sources, index, search_id):
        if search_id != self.current_search_id: return
        try:
            response = requests.get(source['url'], timeout=10)
            response.raise_for_status()
            self.after(0, self._process_image_data, response.content, source, search_id)
        except (requests.RequestException, UnidentifiedImageError) as e:
            print(f"Falha ao carregar {source['type']} de {source['url']}: {e}. Tentando próximo...")
            self.after(0, self._try_next_image_source, all_sources, index + 1, search_id)

    def _process_image_data(self, img_data, source, search_id):
        if search_id != self.current_search_id: 
            self.hide_loading_screen()
            return
        try:
            pil_image = Image.open(BytesIO(img_data))
            if source['type'] == 'gif': self._process_gif(pil_image, search_id)
            else: self._create_static_image(pil_image, source['type'])
        except Exception as e:
            print(f"Erro ao processar imagem: {e}")
            self._handle_image_error(search_id)
        finally:
            if search_id == self.current_search_id:
                self.hide_loading_screen()

    def _process_gif(self, pil_image, search_id):
        self.animation_frames = []
        scale = 3
        try:
            for frame in ImageSequence.Iterator(pil_image):
                duration = frame.info.get('duration', 100)
                ctk_frame = ctk.CTkImage(light_image=frame.convert("RGBA"), size=(frame.width * scale, frame.height * scale))
                self.animation_frames.append((ctk_frame, duration))
            if self.animation_frames: self._animate_gif(0, search_id)
        except Exception as e:
            print(f"Erro ao processar GIF: {e}")
            self._create_static_image(pil_image, 'sprite')

    def _animate_gif(self, frame_index, search_id):
        if search_id != self.current_search_id or not self.animation_frames: return
        frame_image, delay = self.animation_frames[frame_index]
        self.image_label.configure(image=frame_image)
        self.after(delay, self._animate_gif, (frame_index + 1) % len(self.animation_frames), search_id)

    def _create_static_image(self, pil_image, image_type):
        container_size = min(self.image_placeholder.winfo_width(), self.image_placeholder.winfo_height())
        if image_type == 'artwork':
            size = int(container_size * 0.9)
            if size < 1: size = 250
            pil_image.thumbnail((size, size), Image.Resampling.LANCZOS)
            self.pokemon_image = ctk.CTkImage(light_image=pil_image.convert("RGBA"), size=pil_image.size)
        else: # sprite
            scale = 5
            self.pokemon_image = ctk.CTkImage(light_image=pil_image.convert("RGBA"), size=(pil_image.width * scale, pil_image.height * scale))
        self.image_label.configure(image=self.pokemon_image, text="")

    def _handle_image_error(self, search_id):
        if search_id == self.current_search_id:
            self.image_label.configure(image=self.blank_image, text="Erro de imagem")
            self.hide_loading_screen()

    def reset_ui_for_search(self):
        self.animation_frames = [] 
        self.clear_info_panels()
        self.name_label.configure(text="")
        self.image_label.configure(image=self.blank_image, text="")
        self.update_idletasks()

    def clear_info_panels(self):
        self.type1_label.pack_forget()
        self.type2_label.pack_forget()
        self.pokedex_entry_label.configure(text="")
        for stat in self.stat_labels:
            self.stat_bars[stat].set(0)
            self.stat_values[stat].configure(text="")
        for widget in self.locations_frame.winfo_children():
            widget.destroy()
        for widget in self.evolution_frame.winfo_children():
            widget.destroy()

    def refresh_app(self, event=None):
        self.current_search_id += 1
        self.search_entry.delete(0, 'end')
        self.navigation_history.clear()
        self.history_index = -1
        self.update_navigation_buttons_state()
        self.show_home_page()
        self.search_entry.focus_set()

    def show_detail_page(self):
        self.home_page.pack_forget()
        self.search_results_page.pack_forget()
        self.detail_page.pack(fill="both", expand=True)
        self.detail_page.focus_set()

    def show_search_results_page(self):
        self.home_page.pack_forget()
        self.detail_page.pack_forget()
        self.search_results_page.pack(fill="both", expand=True)

    def show_home_page(self):
        self.detail_page.pack_forget()
        self.search_results_page.pack_forget()
        self.home_page.pack(fill="both", expand=True)

    def handle_escape(self, event=None):
        self.go_back()

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        
    def toggle_theme(self):
        if self.theme_switch.get() == 1:
            ctk.set_appearance_mode("dark")
            self.theme_switch.configure(text="Tema Escuro")
        else:
            ctk.set_appearance_mode("light")
            self.theme_switch.configure(text="Tema Claro")
            
    def toggle_shiny(self):
        """Alterna a exibição entre normal e shiny."""
        self.show_shiny = not self.show_shiny
        self.update_shiny_button_color()
        self.update_pokemon_image()

    def update_shiny_button_color(self):
        """Atualiza a cor do botão shiny para indicar se está ativo."""
        if self.show_shiny:
            self.shiny_button.configure(fg_color="#FBC02D", hover_color="#F9A825")
        else:
            self.shiny_button.configure(fg_color=("gray70", "gray25"), hover_color=("gray60", "gray35"))

    def exit_fullscreen(self, event=None):
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.attributes("-fullscreen", False)
    
    def get_text_color(self, bg_color):
        try:
            r, g, b = tuple(int(bg_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
            return "black" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5 else "white"
        except (ValueError, IndexError):
            return "black"

    def next_pokemon_event(self, event=None):
        if not self.detail_page.winfo_ismapped() or self.current_pokedex_id is None: return
        next_id = self.current_pokedex_id + 1
        if next_id <= len(self.all_pokemon_list):
            pokemon_name = self.all_pokemon_list[next_id - 1]['name']
            self.on_result_card_click(pokemon_name)

    def prev_pokemon_event(self, event=None):
        if not self.detail_page.winfo_ismapped() or self.current_pokedex_id is None: return
        prev_id = self.current_pokedex_id - 1
        if prev_id > 0:
            pokemon_name = self.all_pokemon_list[prev_id - 1]['name']
            self.on_result_card_click(pokemon_name)

    def update_pokedex_nav_buttons_state(self):
        if self.current_pokedex_id is not None and self.all_pokemon_list:
            self.prev_pokemon_button.configure(state="normal" if self.current_pokedex_id > 1 else "disabled")
            self.next_pokemon_button.configure(state="normal" if self.current_pokedex_id < len(self.all_pokemon_list) else "disabled")
        else:
            self.prev_pokemon_button.configure(state="disabled")
            self.next_pokemon_button.configure(state="disabled")

if __name__ == "__main__":
    app = PokedexApp()
    app.mainloop()