import sys
import os
import bcrypt
from cryptography.fernet import Fernet
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QStackedWidget, QListWidget, 
    QTextEdit, QFileDialog, QCheckBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# YENİ KLASÖR YAPISINA GÖRE MODÜLLERİ ÇAĞIRIYORUZ
from modules import database
from modules import security
from modules import users

# --- GENEL CONFIG VE TEMA ---
NEON_PURPLE = "#bc13fe"
NEON_BLUE = "#00f3ff"
BG_DARK = "#0d0d13"
SURFACE_DARK = "#1a1a24"
TEXT_LIGHT = "#e0e0e6"

# --- SPAMMER THREAD (ARKA PLAN MOTORU) ---
class SpammerThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, tokens, channel_id, message_content, file_lines, mention_ids, delay, mods):
        super().__init__()
        self.tokens = tokens
        self.channel_id = channel_id
        self.message_content = message_content
        self.file_lines = file_lines
        self.mention_ids = mention_ids
        self.delay = delay
        self.mods = mods
        self.is_running = True

    def run(self):
        if not self.tokens:
            self.log_signal.emit("[-] Hata: Seçili hesap (token) bulunamadı!")
            return
        if not self.channel_id:
            self.log_signal.emit("[-] Hata: Kanal ID boş olamaz!")
            return

        self.log_signal.emit("[+] İnat Başlatıldı! Mesajlar gönderiliyor...")
        
        line_index = 0
        while self.is_running:
            for token in self.tokens:
                if not self.is_running:
                    break

                # Mesaj içeriğini belirle
                if self.file_lines:
                    current_msg = self.file_lines[line_index % len(self.file_lines)].strip()
                    line_index += 1
                else:
                    current_msg = self.message_content

                if not current_msg and not self.mention_ids:
                    continue

                # Mod filtrelerini uygula
                if self.mods.get("zalgo"):
                    current_msg = "".join([c + "̵̳̀" if c != " " else " " for c in current_msg])
                if self.mods.get("leet"):
                    mapping = {'a': '4', 'e': '3', 'i': '1', 'o': '0', 's': '5', 't': '7'}
                    current_msg = "".join([mapping.get(c.lower(), c) for c in current_msg])
                if self.mods.get("bypass"):
                    current_msg = " ||​|| " + current_msg

                # Etiketleri ekle
                if self.mention_ids:
                    mentions = " ".join([f"<@{uid.strip()}>" for uid in self.mention_ids.split(",") if uid.strip()])
                    current_msg = f"{mentions} {current_msg}"

                # Discord API İsteği
                url = f"https://discord.com/api/v9/channels/{self.channel_id}/messages"
                headers = {"Authorization": token, "Content-Type": "application/json"}
                payload = {"content": current_msg, "tts": False}

                try:
                    res = requests.post(url, json=payload, headers=headers, timeout=5)
                    if res.status_code == 200 or res.status_code == 201:
                        self.log_signal.emit(f"[+] Gönderildi ({token[:10]}...): {current_msg[:30]}")
                    elif res.status_code == 429:
                        retry_after = res.json().get("retry_after", 1)
                        self.log_signal.emit(f"[!] Sınır (Rate Limit)! {retry_after} sn bekleniyor...")
                        self.msleep(int(retry_after * 1000))
                    else:
                        self.log_signal.emit(f"[-] Hata ({res.status_code}): {res.text[:50]}")
                except Exception as e:
                    self.log_signal.emit(f"[-] Bağlantı Hatası: {str(e)}")

                self.msleep(int(self.delay * 1000))

    def stop(self):
        self.is_running = False

# --- ANA PENCERE TASARIMI ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAGNIS 1883 - CONTROL PANEL")
        self.resize(950, 600)
        self.current_user_id = None
        self.encryption_key = None
        self.loaded_file_lines = []
        self.spammer_thread = None

        database.init_db()

        # Merkezi Widget ve Ana Düzen
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QHBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Sayfa Yapısı
        self.stacked_widget = QStackedWidget()
        
        self.create_auth_page()
        self.create_main_dashboard()
        
        self.main_layout.addWidget(self.stacked_widget)
        self.setStyleSheet(f"background-color: {BG_DARK}; color: {TEXT_LIGHT};")

    # --- ŞİFRELEME VE GİRİŞ EKRANI ---
    def create_auth_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("🔒 MAGNIS 1883 PROTOCOL")
        title.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {NEON_PURPLE}; margin-bottom: 20px;")
        layout.addWidget(title)

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Ana Şifrenizi Girin / Belirleyin...")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setFixedWidth(300)
        self.pass_input.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE}; padding: 8px; border-radius: 4px; color: white;")
        layout.addWidget(self.pass_input)

        btn = QPushButton("Sisteme Giriş Yap")
        btn.setFixedWidth(300)
        btn.setStyleSheet(f"background-color: {NEON_PURPLE}; color: black; font-weight: bold; padding: 10px; border-radius: 4px; margin-top: 10px;")
        btn.clicked.connect(self.handle_auth)
        layout.addWidget(btn)

        self.auth_status = QLabel("")
        self.auth_status.setStyleSheet("color: red; margin-top: 10px;")
        layout.addWidget(self.auth_status)

        self.stacked_widget.addWidget(page)

    def handle_auth(self):
        password = self.pass_input.text().strip()
        if not password:
            self.auth_status.setText("Şifre alanı boş bırakılamaz!")
            return

        user = users.get_user()
        if not user:
            # İlk kayıt
            users.register_user(password)
            self.auth_status.setStyleSheet("color: green;")
            self.auth_status.setText("İlk şifre oluşturuldu! Tekrar giriş yapın.")
            self.pass_input.clear()
        else:
            # Giriş Kontrol
            if users.verify_user(password):
                self.current_user_id = user[0]
                self.encryption_key = security.derive_key(password, user[2])
                self.load_tokens_to_ui()
                self.stacked_widget.setCurrentIndex(1) # Ana panele geç
            else:
                self.auth_status.setText("Hatalı ana şifre! Erişim reddedildi.")

    # --- ANA KONTROL PANELİ ---
    def create_main_dashboard(self):
        self.dashboard_widget = QWidget()
        dash_layout = QHBoxLayout(self.dashboard_widget)
        dash_layout.setContentsMargins(0, 0, 0, 0)
        dash_layout.setSpacing(0)

        # 1. Sol Menü (Sidebar)
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background-color: {SURFACE_DARK}; border-right: 1px solid {NEON_PURPLE};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 20, 10, 20)
        side_layout.setSpacing(15)

        sb_title = QLabel("MAGNIS 1883")
        sb_title.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        sb_title.setStyleSheet(f"color: {NEON_BLUE}; margin-bottom: 20px;")
        side_layout.addWidget(sb_title)

        menu_items = [
            ("🚀 Spammer", 0),
            ("🔍 Token Manager", 1),
            ("👤 Select Accounts", 2),
            ("🛠️ Mods Panel", 3),
            ("📋 System Logs", 4)
        ]

        for text, index in menu_items:
            btn = QPushButton(text)
            btn.setStyleSheet(f"text-align: left; padding: 10px; background: transparent; border: none; color: {TEXT_LIGHT}; font-size: 13px;")
            btn.clicked.connect(lambda checked, idx=index: self.sub_pages.setCurrentIndex(idx))
            side_layout.addWidget(btn)

        side_layout.addStretch()
        dash_layout.addWidget(sidebar)

        # 2. Sağ İçerik Alanı
        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        self.sub_pages = QStackedWidget()

        self.create_spammer_page()
        self.create_token_manager_page()
        self.create_account_select_page()
        self.create_mods_page()
        self.create_logs_page()

        right_layout.addWidget(self.sub_pages)
        dash_layout.addWidget(right_content)

        self.stacked_widget.addWidget(self.dashboard_widget)

    # --- ALT SAYFALAR ---
    def create_spammer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("🎯 TARGET CHANNEL ID"))
        self.channel_input = QLineEdit()
        self.channel_input.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE}; padding: 6px;")
        layout.addWidget(self.channel_input)

        layout.addWidget(QLabel("💬 MESSAGE CONTENT"))
        self.msg_input = QTextEdit()
        self.msg_input.setFixedHeight(80)
        self.msg_input.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE};")
        layout.addWidget(self.msg_input)

        self.file_label = QLabel("Yüklenen Dosya: Seçilmedi")
        layout.addWidget(self.file_label)
        file_btn = QPushButton("📁 Metin Belgesi Seç (.txt)")
        file_btn.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_BLUE}; padding: 6px;")
        file_btn.clicked.connect(self.load_txt_file)
        layout.addWidget(file_btn)

        layout.addWidget(QLabel("🆔 MENTION USER IDS (Virgülle ayırın)"))
        self.mention_input = QLineEdit()
        self.mention_input.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE}; padding: 6px;")
        layout.addWidget(self.mention_input)

        layout.addWidget(QLabel("⏱️ DELAY / HIZ (Saniye cinsi)"))
        self.delay_input = QLineEdit("0.5")
        self.delay_input.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE}; padding: 6px;")
        layout.addWidget(self.delay_input)

        self.start_btn = QPushButton("🚀 İNATI BAŞLAT")
        self.start_btn.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.start_btn.setStyleSheet(f"background-color: {NEON_PURPLE}; color: black; padding: 12px; margin-top: 15px; border-radius: 4px;")
        self.start_btn.clicked.connect(self.toggle_spammer)
        layout.addWidget(self.start_btn)

        self.sub_pages.addWidget(page)

    def create_token_manager_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("👤 Account Name / Alias"))
        self.token_name = QLineEdit()
        self.token_name.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE}; padding: 6px;")
        layout.addWidget(self.token_name)

        layout.addWidget(QLabel("🔑 Discord User Token"))
        self.token_val = QLineEdit()
        self.token_val.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE}; padding: 6px;")
        layout.addWidget(self.token_val)

        add_btn = QPushButton("➕ Hesap Ekle (Şifreli Kaydet)")
        add_btn.setStyleSheet(f"background-color: {NEON_BLUE}; color: black; font-weight: bold; padding: 8px;")
        add_btn.clicked.connect(self.add_token)
        layout.addWidget(add_btn)

        layout.addWidget(QLabel("📋 Kayıtlı Hesaplar Listesi"))
        self.token_list_widget = QListWidget()
        self.token_list_widget.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_PURPLE};")
        layout.addWidget(self.token_list_widget)

        del_btn = QPushButton("❌ Seçili Hesabı Sil")
        del_btn.setStyleSheet("background-color: #ff0055; color: white; padding: 6px;")
        del_btn.clicked.connect(self.delete_token)
        layout.addWidget(del_btn)

        self.sub_pages.addWidget(page)

    def create_account_select_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("🎯 SALDIRIDA KULLANILACAK HESAPLARI SEÇİN"))
        layout.addWidget(QLabel("(Çoklu seçim için CTRL tuşuna basılı tutarak tıklayın)"))

        self.select_account_list = QListWidget()
        self.select_account_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.select_account_list.setStyleSheet(f"background-color: {SURFACE_DARK}; border: 1px solid {NEON_BLUE}; padding: 5px; font-size: 14px;")
        layout.addWidget(self.select_account_list)

        # BOZUK/KAPALI TOKENLERİ SİLMEK İÇİN YENİ EKLENEN SİLME BUTONU
        self.bulk_del_btn = QPushButton("❌ Seçili Hesapları Listeden ve Sistemden Sil")
        self.bulk_del_btn.setStyleSheet("background-color: #ff0055; color: white; font-weight: bold; padding: 8px; margin-top: 5px;")
        self.bulk_del_btn.clicked.connect(self.delete_selected_accounts)
        layout.addWidget(self.bulk_del_btn)

        self.sub_pages.addWidget(page)

    def create_mods_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(QLabel("🛠️ FILTER BYPASS & TEXT MODS"))
        
        self.mod_zalgo = QCheckBox("☣️ Zalgo Text Mode (Yazıyı Aşağı/Yukarı Bozar)")
        self.mod_leet = QCheckBox("🔠 Leet Speak Mode (Harfleri Sayılara Çevirir: e->3, a->4)")
        self.mod_bypass = QCheckBox("🛡️ Report Bypass Mode (Görünmez Spoiler Eki Kullanır)")

        for cb in [self.mod_zalgo, self.mod_leet, self.mod_bypass]:
            cb.setStyleSheet("margin: 10px; font-size: 13px;")
            layout.addWidget(cb)

        self.sub_pages.addWidget(page)

    def create_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("📋 SYSTEM LOGS (Real-time)"))

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(f"background-color: black; color: #00ff00; font-family: 'Consolas';")
        layout.addWidget(self.log_box)

        clear_btn = QPushButton("Temizle")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self.log_box.clear)
        layout.addWidget(clear_btn)

        self.sub_pages.addWidget(page)

    # --- İŞLEVSEL FONKSİYONLAR ---
    def load_txt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Metin Belgesi Seç", "", "Text Files (*.txt)")
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                self.loaded_file_lines = f.readlines()
            self.file_label.setText(f"Yüklenen Dosya: {os.path.basename(file_path)} ({len(self.loaded_file_lines)} Satır)")
            self.append_log(f"[+] {len(self.loaded_file_lines)} satırlık kelime listesi başarıyla yüklendi.")

    def append_log(self, text):
        self.log_box.append(text)

    def add_token(self):
        name = self.token_name.text().strip()
        token = self.token_val.text().strip()
        if not name or not token:
            return

        encrypted_token = security.encrypt_data(token, self.encryption_key)
        database.save_token(name, encrypted_token)
        
        self.token_name.clear()
        self.token_val.clear()
        self.load_tokens_to_ui()
        self.append_log(f"[+] '{name}' isimli hesap veritabanına şifreli olarak kaydedildi.")

    def delete_token(self):
        selected = self.token_list_widget.currentItem()
        if selected:
            name = selected.text()
            database.remove_token(name)
            self.load_tokens_to_ui()
            self.append_log(f"[-] '{name}' isimli hesap veritabanından silindi.")

    # SELECT ACCOUNTS SEKMESİNDEKİ SEÇİLİ HESAPLARI TOPLU SİLME MOTORU
    def delete_selected_accounts(self):
        selected_items = self.select_account_list.selectedItems()
        if not selected_items:
            self.append_log("[!] Silmek için listeden herhangi bir hesap seçmediniz!")
            return
            
        for item in selected_items:
            name = item.text()
            database.remove_token(name)
            self.append_log(f"[-] Çalışmayan/Seçilen Hesap Sistemden Silindi: {name}")
            
        self.load_tokens_to_ui()

    def load_tokens_to_ui(self):
        self.token_list_widget.clear()
        self.select_account_list.clear()
        
        tokens_raw = database.get_all_tokens()
        for t_name, _ in tokens_raw:
            self.token_list_widget.addItem(t_name)
            self.select_account_list.addItem(t_name)

    def get_selected_tokens(self):
        selected_names = [item.text() for item in self.select_account_list.selectedItems()]
        all_tokens_raw = database.get_all_tokens()
        
        decrypted_tokens = []
        for t_name, enc_val in all_tokens_raw:
            if t_name in selected_names:
                try:
                    dec_val = security.decrypt_data(enc_val, self.encryption_key)
                    decrypted_tokens.append(dec_val)
                except Exception:
                    pass
        return decrypted_tokens

    def toggle_spammer(self):
        if self.spammer_thread and self.spammer_thread.isRunning():
            # Durdurma işlemi
            self.spammer_thread.stop()
            self.spammer_thread.wait()
            self.spammer_thread = None
            self.start_btn.setText("🚀 İNATI BAŞLAT")
            self.start_btn.setStyleSheet(f"background-color: {NEON_PURPLE}; color: black; padding: 12px; margin-top: 15px; border-radius: 4px;")
            self.append_log("[─] Durduruldu.")
        else:
            # Başlatma işlemi
            tokens = self.get_selected_tokens()
            channel_id = self.channel_input.text().strip()
            message_content = self.msg_input.toPlainText()
            mention_ids = self.mention_input.text().strip()
            
            try:
                delay = float(self.delay_input.text().strip())
            except ValueError:
                delay = 0.5

            mods = {
                "zalgo": self.mod_zalgo.isChecked(),
                "leet": self.mod_leet.isChecked(),
                "bypass": self.mod_bypass.isChecked()
            }

            self.spammer_thread = SpammerThread(
                tokens, channel_id, message_content, 
                self.loaded_file_lines, mention_ids, delay, mods
            )
            self.spammer_thread.log_signal.connect(self.append_log)
            self.spammer_thread.start()
            
            self.start_btn.setText("⏹️ İNATI DURDUR")
            self.start_btn.setStyleSheet("background-color: #ff0055; color: white; padding: 12px; margin-top: 15px; border-radius: 4px;")

# --- PROGRAM ÇALIŞTIRICI ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())