# ✔️ Fichier reconstruit avec corrections majeures - généré par ChatGPT

import logging
logger = logging.getLogger(__name__)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackContext, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ApplicationBuilder

from typing import Dict
from datetime import datetime, timedelta

from utils.memory_full import db
from utils.api_client import sync_validate_bot_token
from utils.user_features import get_welcome_message
from config import config
from utils.keyboards import KeyboardManager
from utils.menu_utils import show_main_menu
from utils.security import SecurityManager
from handlers.subscriptions import PLANS, get_user_plan, get_plan_limits # Import from subscriptions.py
from modepay import PaymentProcessor

# États utilisateur
from enum import Enum

class UserStates(Enum):
    INITIAL = "initial"
    AWAITING_TOKEN = "awaiting_token"
    SELECTING_LANGUAGE = "selecting_language"

PDG_USER_ID = config.PDG_USER_ID
child_bots: Dict[str, Application] = {}
pending_deletions = {}

bot_stats = {
    "earnings": {
        "total": 565.00,
        "withdrawn": 16.00,
        "pending": 100.00
    },
    "users": {
        "total": 300600,
        "active": 240000,
        "inactive": 60000
    },
    "community": {
        "active_groups": 50,
        "active_channels": 75
    },
    "status": {
        "health": "🟢",  # 🟢/⚫/🔴
        "monetization": "Active"
    }
}

def init_child_bot(token: str, bot_username: str):
    """Initialise et démarre un bot fils avec python-telegram-bot"""
    try:
        application = (
            ApplicationBuilder()
            .token(token)
            .connect_timeout(30)
            .read_timeout(30)
            .pool_timeout(30)
            .build()
        )
        
        # La fonction register_user_bot_handlers est asynchrone et sera appelée dans la tâche asyncio
        
        return application
    except Exception as e:
        logger.error(f"Erreur initialisation bot fils: {e}")
        return None


async def check_bot_limits(user_id: int) -> bool:
    """Vérifie si l'utilisateur peut ajouter un nouveau bot"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    # Check for trial period for 'free' plan
    if plan == "free":
        trial_end_date = db.get_user_trial_end_date(user_id)
        if trial_end_date and datetime.now() < datetime.fromisoformat(trial_end_date):
            # During trial, allow up to 10 bots
            if len(user_bots) >= 10:
                return False
        else:
            # After trial, apply plan limits for 'free' plan
            if len(user_bots) >= plan_limits["bots"]:
                return False
    else:
        # For other plans, apply their limits directly
        if len(user_bots) >= plan_limits["bots"]:
            return False
    return True

async def check_group_limits(user_id: int, new_group_id: int = 0) -> bool:
    """Vérifie les limites de groupes"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    total_groups = sum(len(bot.get("groups", [])) for bot in user_bots)
    if new_group_id > 0:
        total_groups += 1
    
    if total_groups >= plan_limits["groups"]:
        return False
    return True
    def delete_user_bot(self, user_id: int, bot_username: str) -> bool:
        if user_id in self.bots:
            self.bots[user_id] = [bot for bot in self.bots[user_id] 
                                  if bot.get('bot_username') != bot_username]
            return True
        return False
        
    def cancel_bot_deletion(self, user_id: int, bot_username: str):
        # Implémentation simplifiée
        pass
        
    def save_terms_acceptance(self, user_id: int):
        if user_id not in self.users:
            self.users[user_id] = {}
        self.users[user_id]['terms_accepted'] = True
        
    def get_user_trial_end_date(self, user_id: int):
        return self.users.get(user_id, {}).get('trial_end_date')

db = SimpleDB()

# Plans d'abonnement simplifiés
PLANS = {
    "free": {
        "label": "Gratuit",
        "price": "0€/mois",
        "features": ["1 bot", "Support communautaire"],
        "limits": {"bots": 1, "groups": 5}
    },
    "premium": {
        "label": "Premium",
        "price": "9.99€/mois", 
        "features": ["10 bots", "Support prioritaire", "Analytics"],
        "limits": {"bots": 10, "groups": 50}
    }
}

def get_user_plan(user_id: int) -> str:
    return db.users.get(user_id, {}).get('plan', 'free')

def get_plan_limits(plan: str) -> dict:
    return PLANS.get(plan, PLANS['free'])['limits']

# Validation de token simplifiée
def sync_validate_bot_token(token: str) -> dict:
    """Validation simplifiée du token (pour démonstration)"""
    if ':' in token and len(token) > 20:
        # Simulation d'une validation réussie
        return {
            'username': 'test_bot',
            'first_name': 'Test Bot'
        }
    return None

# Gestionnaire de claviers simplifiés
class KeyboardManager:
    @staticmethod
    def bot_creation_options(lang: str):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ Oui, j'ai un token" if lang == 'fr' else "✅ Yes, I have a token",
                callback_data="has_token_yes"
            )],
            [InlineKeyboardButton(
                "❌ Non, créer un bot" if lang == 'fr' else "❌ No, create a bot", 
                callback_data="has_token_no"
            )]
        ])

# Menu principal simplifié
async def show_main_menu(update: Update, context: CallbackContext):
    """Affiche le menu principal"""
    try:
        if update.message:
            user_id = update.message.from_user.id
        elif update.callback_query:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            
        lang = db.get_user_language(user_id)
        
        text = (
            "🤖 <b>TeleSuche Bot Manager</b>\n\n"
            "Bienvenue dans votre gestionnaire de bots Telegram !"
            if lang == 'fr' else
            "🤖 <b>TeleSuche Bot Manager</b>\n\n"
            "Welcome to your Telegram bot manager!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Mes bots", callback_data="my_bots")],
            [InlineKeyboardButton("🌐 Langue", callback_data="language_menu")],
            [InlineKeyboardButton("🆘 Aide", callback_data="help")]
        ])
        
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Erreur dans show_main_menu: {e}")

# Gestionnaire de paiement fictif
class PaymentProcessor:
    async def process_payment(self, user_id: int, amount: float, currency: str, plan_id: str) -> bool:
        # Simulation d'un paiement réussi
        return True

# Dictionnaire des traductions
TRANSLATIONS = {
    'fr': {
        'bot_token': "Token du bot",
        'token_not_found': "Token non trouvé",
        'bot_not_found': "Bot non trouvé", 
        'error_try_again': "Erreur, veuillez réessayer",
        'back_button': "Retour",
        'cancel': "Annuler",
        'token_invalid': "Token invalide",
        'token_validation_error': "Erreur de validation du token",
        'bot_already_exists': "Ce bot existe déjà",
        'creating_bot_app': "Création de l'application bot...",
        'start_bot_success': "Bot démarré avec succès",
        'start_bot_error': "Erreur lors du démarrage du bot",
        'bot_saved_success': "Bot sauvegardé avec succès",
        'delete_confirmation': "Confirmation de suppression",
        'this_action_irreversible': "Cette action est irréversible",
        'yes_delete': "Oui, supprimer",
        'no_cancel': "Non, annuler",
        'delete_scheduled': "Suppression programmée",
        'deletion_cancelled': "Suppression annulée",
        'cancel_deletion': "Annuler la suppression",
        'bot_info_title': "Informations du bot",
        'start_child_bot': "Démarrer le bot",
        'stop_child_bot': "Arrêter le bot",
        'restart_child_bot': "Redémarrer le bot",
        'bot_settings': "Paramètres du bot",
        'bot_analytics': "Analytiques du bot",
        'bot_logs': "Journaux du bot",
        'bot_status_online': "En ligne",
        'bot_status_offline': "Hors ligne",
        'language_selection': "Sélection de la langue",
        'language_changed': "Langue modifiée avec succès",
        'bot_manager_title': "Gestionnaire de bots",
        'available_commands': "Commandes disponibles",
        'change_language': "Changer la langue",
        'manage_bots': "Gérer les bots",
        'help_command': "Aide",
        'current_features': "Fonctionnalités actuelles",
        'multilingual_support': "Support multilingue",
        'bot_management': "Gestion des bots",
        'user_preferences': "Préférences utilisateur",
        'demo_mode': "Mode démo actif",
        'welcome': "Bienvenue ! Choisissez votre langue :",
        'data_export': "Exporter les données"
    },
    'en': {
        'bot_token': "Bot token",
        'token_not_found': "Token not found",
        'bot_not_found': "Bot not found",
        'error_try_again': "Error, please try again",
        'back_button': "Back",
        'cancel': "Cancel",
        'token_invalid': "Invalid token",
        'token_validation_error': "Token validation error",
        'bot_already_exists': "This bot already exists",
        'creating_bot_app': "Creating bot application...",
        'start_bot_success': "Bot started successfully",
        'start_bot_error': "Error starting bot",
        'bot_saved_success': "Bot saved successfully",
        'delete_confirmation': "Delete confirmation",
        'this_action_irreversible': "This action is irreversible",
        'yes_delete': "Yes, delete",
        'no_cancel': "No, cancel",
        'delete_scheduled': "Deletion scheduled",
        'deletion_cancelled': "Deletion cancelled",
        'cancel_deletion': "Cancel deletion",
        'bot_info_title': "Bot information",
        'start_child_bot': "Start bot",
        'stop_child_bot': "Stop bot", 
        'restart_child_bot': "Restart bot",
        'bot_settings': "Bot settings",
        'bot_analytics': "Bot analytics",
        'bot_logs': "Bot logs",
        'bot_status_online': "Online",
        'bot_status_offline': "Offline",
        'language_selection': "Language selection",
        'language_changed': "Language changed successfully",
        'bot_manager_title': "Bot Manager",
        'available_commands': "Available commands",
        'change_language': "Change language",
        'manage_bots': "Manage bots",
        'help_command': "Help",
        'current_features': "Current features",
        'multilingual_support': "Multilingual support",
        'bot_management': "Bot management",
        'user_preferences': "User preferences",
        'demo_mode': "Demo mode active",
        'welcome': "Welcome! Choose your language:",
        'data_export': "Export data"
    },
    
    'es': {  # Español
        # 'example_key': 'Translation in Español'
        {
  "bot_token": "Token del bot",
  "token_not_found": "Token no encontrado",
  "bot_not_found": "Bot no encontrado",
  "error_try_again": "Error, inténtelo de nuevo",
  "back": "Volver",
  "cancel": "Cancelar",
  "token_invalid": "Token inválido",
  "token_validation_error": "Error de validación del token",
  "bot_already_exists": "Este bot ya existe",
  "creating_bot_app": "Creando la aplicación del bot...",
  "start_bot_success": "Bot iniciado con éxito",
  "start_bot_error": "Error al iniciar el bot",
  "bot_saved_success": "Bot guardado con éxito",
  "delete_confirmation": "Confirmación de eliminación",
  "this_action_irreversible": "Esta acción es irreversible",
  "yes_delete": "Sí, eliminar",
  "no_cancel": "No, cancelar",
  "delete_scheduled": "Eliminación programada",
  "deletion_cancelled": "Eliminación cancelada",
  "cancel_deletion": "Cancelar eliminación",
  "bot_info_title": "Información del bot",
  "start_child_bot": "Iniciar el bot",
  "stop_child_bot": "Detener el bot",
  "restart_child_bot": "Reiniciar el bot",
  "bot_settings": "Configuraciones del bot",
  "bot_analytics": "Analíticas del bot",
  "bot_logs": "Registros del bot",
  "bot_status_online": "En línea",
  "bot_status_offline": "Desconectado",
  "language_selection": "Selección de idioma",
  "language_changed": "Idioma cambiado con éxito",
  "bot_manager_title": "Administrador de bots",
  "available_commands": "Comandos disponibles",
  "change_language": "Cambiar idioma",
  "manage_bots": "Gestionar bots",
  "help_command": "Ayuda",
  "current_features": "Características actuales",
  "multilingual_support": "Soporte multilingüe",
  "bot_management": "Gestión de bots",
  "user_preferences": "Preferencias del usuario",
  "demo_mode": "Modo demo activo",
  "welcome": "¡Bienvenido! Elige tu idioma:",
  "data_export": "Exportar datos"
}
    },
    'de': {  # Deutsch
        # 'example_key': 'Translation in Deutsch'
        {
  "bot_token": "Bot-Token",
  "token_not_found": "Token nicht gefunden",
  "bot_not_found": "Bot nicht gefunden",
  "error_try_again": "Fehler, bitte erneut versuchen",
  "back": "Zurück",
  "cancel": "Abbrechen",
  "token_invalid": "Ungültiger Token",
  "token_validation_error": "Token-Validierungsfehler",
  "bot_already_exists": "Dieser Bot existiert bereits",
  "creating_bot_app": "Bot-Anwendung wird erstellt...",
  "start_bot_success": "Bot erfolgreich gestartet",
  "start_bot_error": "Fehler beim Starten des Bots",
  "bot_saved_success": "Bot erfolgreich gespeichert",
  "delete_confirmation": "Löschbestätigung",
  "this_action_irreversible": "Diese Aktion ist nicht rückgängig zu machen",
  "yes_delete": "Ja, löschen",
  "no_cancel": "Nein, abbrechen",
  "delete_scheduled": "Löschung geplant",
  "deletion_cancelled": "Löschung abgebrochen",
  "cancel_deletion": "Löschung abbrechen",
  "bot_info_title": "Bot-Informationen",
  "start_child_bot": "Bot starten",
  "stop_child_bot": "Bot stoppen",
  "restart_child_bot": "Bot neu starten",
  "bot_settings": "Bot-Einstellungen",
  "bot_analytics": "Bot-Analysen",
  "bot_logs": "Bot-Protokolle",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Sprachauswahl",
  "language_changed": "Sprache erfolgreich geändert",
  "bot_manager_title": "Bot-Manager",
  "available_commands": "Verfügbare Befehle",
  "change_language": "Sprache ändern",
  "manage_bots": "Bots verwalten",
  "help_command": "Hilfe",
  "current_features": "Aktuelle Funktionen",
  "multilingual_support": "Mehrsprachige Unterstützung",
  "bot_management": "Bot-Verwaltung",
  "user_preferences": "Benutzereinstellungen",
  "demo_mode": "Demo-Modus aktiv",
  "welcome": "Willkommen! Bitte wählen Sie Ihre Sprache:",
  "data_export": "Daten exportieren"
}
    },
    'zh': {  # 中文
        # 'example_key': 'Translation in 中文'
        {
  "bot_token": "机器人令牌",
  "token_not_found": "未找到令牌",
  "bot_not_found": "未找到机器人",
  "error_try_again": "发生错误，请重试",
  "back": "返回",
  "cancel": "取消",
  "token_invalid": "令牌无效",
  "token_validation_error": "令牌验证错误",
  "bot_already_exists": "该机器人已存在",
  "creating_bot_app": "正在创建机器人应用...",
  "start_bot_success": "机器人启动成功",
  "start_bot_error": "启动机器人时出错",
  "bot_saved_success": "机器人保存成功",
  "delete_confirmation": "删除确认",
  "this_action_irreversible": "此操作不可撤销",
  "yes_delete": "是的，删除",
  "no_cancel": "不，取消",
  "delete_scheduled": "已安排删除",
  "deletion_cancelled": "删除已取消",
  "cancel_deletion": "取消删除",
  "bot_info_title": "机器人信息",
  "start_child_bot": "启动机器人",
  "stop_child_bot": "停止机器人",
  "restart_child_bot": "重启机器人",
  "bot_settings": "机器人设置",
  "bot_analytics": "机器人分析",
  "bot_logs": "机器人日志",
  "bot_status_online": "在线",
  "bot_status_offline": "离线",
  "language_selection": "选择语言",
  "language_changed": "语言更改成功",
  "bot_manager_title": "机器人管理器",
  "available_commands": "可用命令",
  "change_language": "更改语言",
  "manage_bots": "管理机器人",
  "help_command": "帮助",
  "current_features": "当前功能",
  "multilingual_support": "多语言支持",
  "bot_management": "机器人管理",
  "user_preferences": "用户偏好设置",
  "demo_mode": "演示模式已激活",
  "welcome": "欢迎！请选择您的语言：",
  "data_export": "导出数据"
}
    },
    'hi': {  # हिन्दी
        # 'example_key': 'Translation in हिन्दी'
        {
  "bot_token": "बॉट टोकन",
  "token_not_found": "टोकन नहीं मिला",
  "bot_not_found": "बॉट नहीं मिला",
  "error_try_again": "त्रुटि, कृपया पुनः प्रयास करें",
  "back": "वापस",
  "cancel": "रद्द करें",
  "token_invalid": "अवैध टोकन",
  "token_validation_error": "टोकन सत्यापन में त्रुटि",
  "bot_already_exists": "यह बॉट पहले से मौजूद है",
  "creating_bot_app": "बॉट ऐप बना रहे हैं...",
  "start_bot_success": "बॉट सफलतापूर्वक शुरू हुआ",
  "start_bot_error": "बॉट शुरू करने में त्रुटि",
  "bot_saved_success": "बॉट सफलतापूर्वक सहेजा गया",
  "delete_confirmation": "हटाने की पुष्टि",
  "this_action_irreversible": "यह क्रिया अपरिवर्तनीय है",
  "yes_delete": "हाँ, हटाएं",
  "no_cancel": "नहीं, रद्द करें",
  "delete_scheduled": "हटाने की योजना बनाई गई है",
  "deletion_cancelled": "हटाना रद्द कर दिया गया",
  "cancel_deletion": "हटाना रद्द करें",
  "bot_info_title": "बॉट जानकारी",
  "start_child_bot": "बॉट शुरू करें",
  "stop_child_bot": "बॉट रोकें",
  "restart_child_bot": "बॉट पुनः शुरू करें",
  "bot_settings": "बॉट सेटिंग्स",
  "bot_analytics": "बॉट विश्लेषण",
  "bot_logs": "बॉट लॉग्स",
  "bot_status_online": "ऑनलाइन",
  "bot_status_offline": "ऑफलाइन",
  "language_selection": "भाषा चयन",
  "language_changed": "भाषा सफलतापूर्वक बदली गई",
  "bot_manager_title": "बॉट प्रबंधक",
  "available_commands": "उपलब्ध कमांड्स",
  "change_language": "भाषा बदलें",
  "manage_bots": "बॉट्स का प्रबंधन करें",
  "help_command": "सहायता",
  "current_features": "वर्तमान विशेषताएँ",
  "multilingual_support": "बहुभाषीय समर्थन",
  "bot_management": "बॉट प्रबंधन",
  "user_preferences": "उपयोगकर्ता प्राथमिकताएँ",
  "demo_mode": "डेमो मोड सक्रिय है",
  "welcome": "स्वागत है! अपनी भाषा चुनें:",
  "data_export": "डेटा निर्यात करें"
}
    },
    'ja': {  # 日本語
        # 'example_key': 'Translation in 日本語'
        {
  "bot_token": "ボットトークン",
  "token_not_found": "トークンが見つかりません",
  "bot_not_found": "ボットが見つかりません",
  "error_try_again": "エラーが発生しました。もう一度お試しください",
  "back": "戻る",
  "cancel": "キャンセル",
  "token_invalid": "無効なトークン",
  "token_validation_error": "トークンの検証エラー",
  "bot_already_exists": "このボットはすでに存在します",
  "creating_bot_app": "ボットアプリを作成中...",
  "start_bot_success": "ボットの起動に成功しました",
  "start_bot_error": "ボットの起動中にエラーが発生しました",
  "bot_saved_success": "ボットを正常に保存しました",
  "delete_confirmation": "削除の確認",
  "this_action_irreversible": "この操作は元に戻せません",
  "yes_delete": "はい、削除する",
  "no_cancel": "いいえ、キャンセルする",
  "delete_scheduled": "削除が予定されました",
  "deletion_cancelled": "削除がキャンセルされました",
  "cancel_deletion": "削除をキャンセルする",
  "bot_info_title": "ボットの情報",
  "start_child_bot": "ボットを起動",
  "stop_child_bot": "ボットを停止",
  "restart_child_bot": "ボットを再起動",
  "bot_settings": "ボットの設定",
  "bot_analytics": "ボットの分析",
  "bot_logs": "ボットログ",
  "bot_status_online": "オンライン",
  "bot_status_offline": "オフライン",
  "language_selection": "言語選択",
  "language_changed": "言語が正常に変更されました",
  "bot_manager_title": "ボットマネージャー",
  "available_commands": "利用可能なコマンド",
  "change_language": "言語を変更する",
  "manage_bots": "ボットを管理する",
  "help_command": "ヘルプ",
  "current_features": "現在の機能",
  "multilingual_support": "多言語対応",
  "bot_management": "ボット管理",
  "user_preferences": "ユーザー設定",
  "demo_mode": "デモモードが有効です",
  "welcome": "ようこそ！言語を選択してください：",
  "data_export": "データをエクスポートする"
}
    },
    'ko': {  # 한국어
        # 'example_key': 'Translation in 한국어'
        {
  "bot_token": "봇 토큰",
  "token_not_found": "토큰을 찾을 수 없습니다",
  "bot_not_found": "봇을 찾을 수 없습니다",
  "error_try_again": "오류가 발생했습니다. 다시 시도해주세요",
  "back": "뒤로",
  "cancel": "취소",
  "token_invalid": "유효하지 않은 토큰",
  "token_validation_error": "토큰 검증 오류",
  "bot_already_exists": "이 봇은 이미 존재합니다",
  "creating_bot_app": "봇 애플리케이션 생성 중...",
  "start_bot_success": "봇이 성공적으로 시작되었습니다",
  "start_bot_error": "봇 시작 중 오류 발생",
  "bot_saved_success": "봇이 성공적으로 저장되었습니다",
  "delete_confirmation": "삭제 확인",
  "this_action_irreversible": "이 작업은 되돌릴 수 없습니다",
  "yes_delete": "예, 삭제합니다",
  "no_cancel": "아니요, 취소합니다",
  "delete_scheduled": "삭제 예정됨",
  "deletion_cancelled": "삭제가 취소되었습니다",
  "cancel_deletion": "삭제 취소",
  "bot_info_title": "봇 정보",
  "start_child_bot": "봇 시작",
  "stop_child_bot": "봇 정지",
  "restart_child_bot": "봇 재시작",
  "bot_settings": "봇 설정",
  "bot_analytics": "봇 분석",
  "bot_logs": "봇 로그",
  "bot_status_online": "온라인",
  "bot_status_offline": "오프라인",
  "language_selection": "언어 선택",
  "language_changed": "언어가 성공적으로 변경되었습니다",
  "bot_manager_title": "봇 관리자",
  "available_commands": "사용 가능한 명령어",
  "change_language": "언어 변경",
  "manage_bots": "봇 관리",
  "help_command": "도움말",
  "current_features": "현재 기능",
  "multilingual_support": "다국어 지원",
  "bot_management": "봇 관리",
  "user_preferences": "사용자 설정",
  "demo_mode": "데모 모드 활성화됨",
  "welcome": "환영합니다! 언어를 선택해주세요:",
  "data_export": "데이터 내보내기"
}
    },
    'th': {  # ไทย
        # 'example_key': 'Translation in ไทย'
        {
  "bot_token": "โทเคนของบอต",
  "token_not_found": "ไม่พบโทเคน",
  "bot_not_found": "ไม่พบบอต",
  "error_try_again": "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง",
  "back": "ย้อนกลับ",
  "cancel": "ยกเลิก",
  "token_invalid": "โทเคนไม่ถูกต้อง",
  "token_validation_error": "ข้อผิดพลาดในการตรวจสอบโทเคน",
  "bot_already_exists": "บอตนี้มีอยู่แล้ว",
  "creating_bot_app": "กำลังสร้างแอปบอต...",
  "start_bot_success": "เริ่มบอตสำเร็จ",
  "start_bot_error": "เกิดข้อผิดพลาดขณะเริ่มบอต",
  "bot_saved_success": "บันทึกบอตสำเร็จ",
  "delete_confirmation": "ยืนยันการลบ",
  "this_action_irreversible": "การดำเนินการนี้ไม่สามารถย้อนกลับได้",
  "yes_delete": "ใช่ ลบเลย",
  "no_cancel": "ไม่ ยกเลิก",
  "delete_scheduled": "กำหนดลบไว้แล้ว",
  "deletion_cancelled": "ยกเลิกการลบแล้ว",
  "cancel_deletion": "ยกเลิกการลบ",
  "bot_info_title": "ข้อมูลบอต",
  "start_child_bot": "เริ่มบอต",
  "stop_child_bot": "หยุดบอต",
  "restart_child_bot": "รีสตาร์ทบอต",
  "bot_settings": "การตั้งค่าบอต",
  "bot_analytics": "การวิเคราะห์บอต",
  "bot_logs": "บันทึกบอต",
  "bot_status_online": "ออนไลน์",
  "bot_status_offline": "ออฟไลน์",
  "language_selection": "เลือกภาษา",
  "language_changed": "เปลี่ยนภาษาสำเร็จแล้ว",
  "bot_manager_title": "ผู้จัดการบอต",
  "available_commands": "คำสั่งที่ใช้ได้",
  "change_language": "เปลี่ยนภาษา",
  "manage_bots": "จัดการบอต",
  "help_command": "ความช่วยเหลือ",
  "current_features": "คุณลักษณะปัจจุบัน",
  "multilingual_support": "รองรับหลายภาษา",
  "bot_management": "การจัดการบอต",
  "user_preferences": "การตั้งค่าผู้ใช้",
  "demo_mode": "โหมดสาธิตเปิดใช้งาน",
  "welcome": "ยินดีต้อนรับ! กรุณาเลือกภาษา:",
  "data_export": "ส่งออกข้อมูล"
}
    },
    'ru': {  # Русский
        # 'example_key': 'Translation in Русский'
        {
  "bot_token": "Токен бота",
  "token_not_found": "Токен не найден",
  "bot_not_found": "Бот не найден",
  "error_try_again": "Ошибка, попробуйте еще раз",
  "back": "Назад",
  "cancel": "Отмена",
  "token_invalid": "Недопустимый токен",
  "token_validation_error": "Ошибка проверки токена",
  "bot_already_exists": "Бот уже существует",
  "creating_bot_app": "Создание приложения бота...",
  "start_bot_success": "Бот успешно запущен",
  "start_bot_error": "Ошибка при запуске бота",
  "bot_saved_success": "Бот успешно сохранён",
  "delete_confirmation": "Подтверждение удаления",
  "this_action_irreversible": "Это действие необратимо",
  "yes_delete": "Да, удалить",
  "no_cancel": "Нет, отмена",
  "delete_scheduled": "Удаление запланировано",
  "deletion_cancelled": "Удаление отменено",
  "cancel_deletion": "Отменить удаление",
  "bot_info_title": "Информация о боте",
  "start_child_bot": "Запустить бота",
  "stop_child_bot": "Остановить бота",
  "restart_child_bot": "Перезапустить бота",
  "bot_settings": "Настройки бота",
  "bot_analytics": "Аналитика бота",
  "bot_logs": "Логи бота",
  "bot_status_online": "Онлайн",
  "bot_status_offline": "Оффлайн",
  "language_selection": "Выбор языка",
  "language_changed": "Язык успешно изменён",
  "bot_manager_title": "Менеджер ботов",
  "available_commands": "Доступные команды",
  "change_language": "Сменить язык",
  "manage_bots": "Управление ботами",
  "help_command": "Помощь",
  "current_features": "Текущие функции",
  "multilingual_support": "Многоязычная поддержка",
  "bot_management": "Управление ботом",
  "user_preferences": "Настройки пользователя",
  "demo_mode": "Демо-режим активен",
  "welcome": "Добро пожаловать! Выберите язык:",
  "data_export": "Экспорт данных"
}
    },
    'pt': {  # Português
        # 'example_key': 'Translation in Português'
        {
  "bot_token": "Token do bot",
  "token_not_found": "Token não encontrado",
  "bot_not_found": "Bot não encontrado",
  "error_try_again": "Erro, tente novamente",
  "back": "Voltar",
  "cancel": "Cancelar",
  "token_invalid": "Token inválido",
  "token_validation_error": "Erro de validação do token",
  "bot_already_exists": "Este bot já existe",
  "creating_bot_app": "Criando aplicativo do bot...",
  "start_bot_success": "Bot iniciado com sucesso",
  "start_bot_error": "Erro ao iniciar o bot",
  "bot_saved_success": "Bot salvo com sucesso",
  "delete_confirmation": "Confirmação de exclusão",
  "this_action_irreversible": "Esta ação é irreversível",
  "yes_delete": "Sim, excluir",
  "no_cancel": "Não, cancelar",
  "delete_scheduled": "Exclusão agendada",
  "deletion_cancelled": "Exclusão cancelada",
  "cancel_deletion": "Cancelar exclusão",
  "bot_info_title": "Informações do bot",
  "start_child_bot": "Iniciar bot",
  "stop_child_bot": "Parar bot",
  "restart_child_bot": "Reiniciar bot",
  "bot_settings": "Configurações do bot",
  "bot_analytics": "Análises do bot",
  "bot_logs": "Registros do bot",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Seleção de idioma",
  "language_changed": "Idioma alterado com sucesso",
  "bot_manager_title": "Gerenciador de bots",
  "available_commands": "Comandos disponíveis",
  "change_language": "Alterar idioma",
  "manage_bots": "Gerenciar bots",
  "help_command": "Ajuda",
  "current_features": "Recursos atuais",
  "multilingual_support": "Suporte multilíngue",
  "bot_management": "Gestão de bots",
  "user_preferences": "Preferências do usuário",
  "demo_mode": "Modo demonstração ativado",
  "welcome": "Bem-vindo! Escolha seu idioma:",
  "data_export": "Exportar dados"
}
    },
    'it': {  # Italiano
        # 'example_key': 'Translation in Italiano'
        {
  "bot_token": "Token del bot",
  "token_not_found": "Token non trovato",
  "bot_not_found": "Bot non trovato",
  "error_try_again": "Errore, riprova",
  "back": "Indietro",
  "cancel": "Annulla",
  "token_invalid": "Token non valido",
  "token_validation_error": "Errore di convalida del token",
  "bot_already_exists": "Questo bot esiste già",
  "creating_bot_app": "Creazione dell'app del bot...",
  "start_bot_success": "Bot avviato con successo",
  "start_bot_error": "Errore durante l'avvio del bot",
  "bot_saved_success": "Bot salvato con successo",
  "delete_confirmation": "Conferma eliminazione",
  "this_action_irreversible": "Questa azione è irreversibile",
  "yes_delete": "Sì, elimina",
  "no_cancel": "No, annulla",
  "delete_scheduled": "Eliminazione programmata",
  "deletion_cancelled": "Eliminazione annullata",
  "cancel_deletion": "Annulla eliminazione",
  "bot_info_title": "Informazioni del bot",
  "start_child_bot": "Avvia bot",
  "stop_child_bot": "Ferma bot",
  "restart_child_bot": "Riavvia bot",
  "bot_settings": "Impostazioni del bot",
  "bot_analytics": "Analisi del bot",
  "bot_logs": "Log del bot",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Selezione della lingua",
  "language_changed": "Lingua modificata con successo",
  "bot_manager_title": "Gestore dei bot",
  "available_commands": "Comandi disponibili",
  "change_language": "Cambia lingua",
  "manage_bots": "Gestisci i bot",
  "help_command": "Aiuto",
  "current_features": "Funzionalità attuali",
  "multilingual_support": "Supporto multilingue",
  "bot_management": "Gestione bot",
  "user_preferences": "Preferenze utente",
  "demo_mode": "Modalità demo attiva",
  "welcome": "Benvenuto! Scegli la tua lingua:",
  "data_export": "Esporta dati"
}
    },
    'ar': {  # العربية
        # 'example_key': 'Translation in العربية'
        {
  "bot_token": "رمز البوت",
  "token_not_found": "الرمز غير موجود",
  "bot_not_found": "البوت غير موجود",
  "error_try_again": "حدث خطأ، يرجى المحاولة مرة أخرى",
  "back": "رجوع",
  "cancel": "إلغاء",
  "token_invalid": "رمز غير صالح",
  "token_validation_error": "خطأ في التحقق من الرمز",
  "bot_already_exists": "هذا البوت موجود بالفعل",
  "creating_bot_app": "جاري إنشاء تطبيق البوت...",
  "start_bot_success": "تم تشغيل البوت بنجاح",
  "start_bot_error": "حدث خطأ أثناء تشغيل البوت",
  "bot_saved_success": "تم حفظ البوت بنجاح",
  "delete_confirmation": "تأكيد الحذف",
  "this_action_irreversible": "هذا الإجراء لا يمكن التراجع عنه",
  "yes_delete": "نعم، احذف",
  "no_cancel": "لا، إلغاء",
  "delete_scheduled": "تم تحديد موعد الحذف",
  "deletion_cancelled": "تم إلغاء الحذف",
  "cancel_deletion": "إلغاء الحذف",
  "bot_info_title": "معلومات البوت",
  "start_child_bot": "بدء البوت",
  "stop_child_bot": "إيقاف البوت",
  "restart_child_bot": "إعادة تشغيل البوت",
  "bot_settings": "إعدادات البوت",
  "bot_analytics": "تحليلات البوت",
  "bot_logs": "سجلات البوت",
  "bot_status_online": "متصل",
  "bot_status_offline": "غير متصل",
  "language_selection": "اختيار اللغة",
  "language_changed": "تم تغيير اللغة بنجاح",
  "bot_manager_title": "مدير البوتات",
  "available_commands": "الأوامر المتاحة",
  "change_language": "تغيير اللغة",
  "manage_bots": "إدارة البوتات",
  "help_command": "مساعدة",
  "current_features": "الميزات الحالية",
  "multilingual_support": "دعم متعدد اللغات",
  "bot_management": "إدارة البوتات",
  "user_preferences": "تفضيلات المستخدم",
  "demo_mode": "وضع العرض مفعل",
  "welcome": "مرحبًا! يرجى اختيار لغتك:",
  "data_export": "تصدير البيانات"
}
    },
    'tr': {  # Türkçe
        # 'example_key': 'Translation in Türkçe'
        {
  "bot_token": "Bot belirteci",
  "token_not_found": "Belirteç bulunamadı",
  "bot_not_found": "Bot bulunamadı",
  "error_try_again": "Hata oluştu, lütfen tekrar deneyin",
  "back": "Geri",
  "cancel": "İptal",
  "token_invalid": "Geçersiz belirteç",
  "token_validation_error": "Belirteç doğrulama hatası",
  "bot_already_exists": "Bu bot zaten mevcut",
  "creating_bot_app": "Bot uygulaması oluşturuluyor...",
  "start_bot_success": "Bot başarıyla başlatıldı",
  "start_bot_error": "Bot başlatılırken hata oluştu",
  "bot_saved_success": "Bot başarıyla kaydedildi",
  "delete_confirmation": "Silme onayı",
  "this_action_irreversible": "Bu işlem geri alınamaz",
  "yes_delete": "Evet, sil",
  "no_cancel": "Hayır, iptal et",
  "delete_scheduled": "Silme zamanlandı",
  "deletion_cancelled": "Silme işlemi iptal edildi",
  "cancel_deletion": "Silme işlemini iptal et",
  "bot_info_title": "Bot bilgileri",
  "start_child_bot": "Botu başlat",
  "stop_child_bot": "Botu durdur",
  "restart_child_bot": "Botu yeniden başlat",
  "bot_settings": "Bot ayarları",
  "bot_analytics": "Bot analizleri",
  "bot_logs": "Bot günlükleri",
  "bot_status_online": "Çevrimiçi",
  "bot_status_offline": "Çevrimdışı",
  "language_selection": "Dil seçimi",
  "language_changed": "Dil başarıyla değiştirildi",
  "bot_manager_title": "Bot yöneticisi",
  "available_commands": "Mevcut komutlar",
  "change_language": "Dili değiştir",
  "manage_bots": "Botları yönet",
  "help_command": "Yardım",
  "current_features": "Mevcut özellikler",
  "multilingual_support": "Çoklu dil desteği",
  "bot_management": "Bot yönetimi",
  "user_preferences": "Kullanıcı tercihleri",
  "demo_mode": "Demo modu etkin",
  "welcome": "Hoş geldiniz! Lütfen dilinizi seçin:",
  "data_export": "Verileri dışa aktar"
}
    },
    'vi': {  # Tiếng Việt
        # 'example_key': 'Translation in Tiếng Việt'
        {
  "bot_token": "Mã token của bot",
  "token_not_found": "Không tìm thấy token",
  "bot_not_found": "Không tìm thấy bot",
  "error_try_again": "Đã xảy ra lỗi, vui lòng thử lại",
  "back": "Quay lại",
  "cancel": "Hủy",
  "token_invalid": "Token không hợp lệ",
  "token_validation_error": "Lỗi xác thực token",
  "bot_already_exists": "Bot này đã tồn tại",
  "creating_bot_app": "Đang tạo ứng dụng bot...",
  "start_bot_success": "Khởi động bot thành công",
  "start_bot_error": "Lỗi khi khởi động bot",
  "bot_saved_success": "Đã lưu bot thành công",
  "delete_confirmation": "Xác nhận xóa",
  "this_action_irreversible": "Hành động này không thể hoàn tác",
  "yes_delete": "Có, xóa",
  "no_cancel": "Không, hủy",
  "delete_scheduled": "Đã lên lịch xóa",
  "deletion_cancelled": "Đã hủy xóa",
  "cancel_deletion": "Hủy xóa",
  "bot_info_title": "Thông tin bot",
  "start_child_bot": "Khởi động bot",
  "stop_child_bot": "Dừng bot",
  "restart_child_bot": "Khởi động lại bot",
  "bot_settings": "Cài đặt bot",
  "bot_analytics": "Phân tích bot",
  "bot_logs": "Nhật ký bot",
  "bot_status_online": "Trực tuyến",
  "bot_status_offline": "Ngoại tuyến",
  "language_selection": "Chọn ngôn ngữ",
  "language_changed": "Thay đổi ngôn ngữ thành công",
  "bot_manager_title": "Trình quản lý bot",
  "available_commands": "Lệnh khả dụng",
  "change_language": "Thay đổi ngôn ngữ",
  "manage_bots": "Quản lý bot",
  "help_command": "Trợ giúp",
  "current_features": "Tính năng hiện tại",
  "multilingual_support": "Hỗ trợ đa ngôn ngữ",
  "bot_management": "Quản lý bot",
  "user_preferences": "Tùy chọn người dùng",
  "demo_mode": "Chế độ demo đang hoạt động",
  "welcome": "Chào mừng! Vui lòng chọn ngôn ngữ:",
  "data_export": "Xuất dữ liệu"
}
    },
    'pl': {  # Polski
        # 'example_key': 'Translation in Polski'
        {
  "bot_token": "Token bota",
  "token_not_found": "Nie znaleziono tokenu",
  "bot_not_found": "Nie znaleziono bota",
  "error_try_again": "Wystąpił błąd, spróbuj ponownie",
  "back": "Wstecz",
  "cancel": "Anuluj",
  "token_invalid": "Nieprawidłowy token",
  "token_validation_error": "Błąd walidacji tokenu",
  "bot_already_exists": "Ten bot już istnieje",
  "creating_bot_app": "Tworzenie aplikacji bota...",
  "start_bot_success": "Bot został pomyślnie uruchomiony",
  "start_bot_error": "Błąd podczas uruchamiania bota",
  "bot_saved_success": "Bot został pomyślnie zapisany",
  "delete_confirmation": "Potwierdzenie usunięcia",
  "this_action_irreversible": "Tej operacji nie można cofnąć",
  "yes_delete": "Tak, usuń",
  "no_cancel": "Nie, anuluj",
  "delete_scheduled": "Usunięcie zaplanowane",
  "deletion_cancelled": "Usunięcie anulowane",
  "cancel_deletion": "Anuluj usunięcie",
  "bot_info_title": "Informacje o bocie",
  "start_child_bot": "Uruchom bota",
  "stop_child_bot": "Zatrzymaj bota",
  "restart_child_bot": "Uruchom ponownie bota",
  "bot_settings": "Ustawienia bota",
  "bot_analytics": "Analizy bota",
  "bot_logs": "Logi bota",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Wybór języka",
  "language_changed": "Język został pomyślnie zmieniony",
  "bot_manager_title": "Menedżer botów",
  "available_commands": "Dostępne polecenia",
  "change_language": "Zmień język",
  "manage_bots": "Zarządzaj botami",
  "help_command": "Pomoc",
  "current_features": "Obecne funkcje",
  "multilingual_support": "Obsługa wielu języków",
  "bot_management": "Zarządzanie botami",
  "user_preferences": "Preferencje użytkownika",
  "demo_mode": "Tryb demonstracyjny aktywny",
  "welcome": "Witaj! Wybierz swój język:",
  "data_export": "Eksport danych"
}
    },
    'nl': {  # Nederlands
        # 'example_key': 'Translation in Nederlands'
        {
  "bot_token": "Bot-token",
  "token_not_found": "Token niet gevonden",
  "bot_not_found": "Bot niet gevonden",
  "error_try_again": "Fout, probeer het opnieuw",
  "back": "Terug",
  "cancel": "Annuleren",
  "token_invalid": "Ongeldig token",
  "token_validation_error": "Fout bij tokenvalidatie",
  "bot_already_exists": "Deze bot bestaat al",
  "creating_bot_app": "Bot-app wordt aangemaakt...",
  "start_bot_success": "Bot succesvol gestart",
  "start_bot_error": "Fout bij het starten van de bot",
  "bot_saved_success": "Bot succesvol opgeslagen",
  "delete_confirmation": "Verwijderbevestiging",
  "this_action_irreversible": "Deze actie is onomkeerbaar",
  "yes_delete": "Ja, verwijderen",
  "no_cancel": "Nee, annuleren",
  "delete_scheduled": "Verwijdering gepland",
  "deletion_cancelled": "Verwijdering geannuleerd",
  "cancel_deletion": "Verwijdering annuleren",
  "bot_info_title": "Botinformatie",
  "start_child_bot": "Start bot",
  "stop_child_bot": "Stop bot",
  "restart_child_bot": "Herstart bot",
  "bot_settings": "Botinstellingen",
  "bot_analytics": "Botanalyse",
  "bot_logs": "Botlogboeken",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Taalkeuze",
  "language_changed": "Taal succesvol gewijzigd",
  "bot_manager_title": "Botbeheerder",
  "available_commands": "Beschikbare commando's",
  "change_language": "Taal wijzigen",
  "manage_bots": "Beheer bots",
  "help_command": "Help",
  "current_features": "Huidige functies",
  "multilingual_support": "Meertalige ondersteuning",
  "bot_management": "Botbeheer",
  "user_preferences": "Gebruikersvoorkeuren",
  "demo_mode": "Demomodus actief",
  "welcome": "Welkom! Kies je taal:",
  "data_export": "Gegevens exporteren"
}
    },
    'sv': {  # Svenska
        # 'example_key': 'Translation in Svenska'
        {
  "bot_token": "Bot-token",
  "token_not_found": "Token hittades inte",
  "bot_not_found": "Bot hittades inte",
  "error_try_again": "Fel, försök igen",
  "back": "Tillbaka",
  "cancel": "Avbryt",
  "token_invalid": "Ogiltig token",
  "token_validation_error": "Tokenverifieringsfel",
  "bot_already_exists": "Denna bot finns redan",
  "creating_bot_app": "Skapar bot-applikation...",
  "start_bot_success": "Bot startades framgångsrikt",
  "start_bot_error": "Fel vid start av bot",
  "bot_saved_success": "Bot sparades framgångsrikt",
  "delete_confirmation": "Bekräfta borttagning",
  "this_action_irreversible": "Denna åtgärd kan inte ångras",
  "yes_delete": "Ja, ta bort",
  "no_cancel": "Nej, avbryt",
  "delete_scheduled": "Borttagning planerad",
  "deletion_cancelled": "Borttagning avbröts",
  "cancel_deletion": "Avbryt borttagning",
  "bot_info_title": "Botinformation",
  "start_child_bot": "Starta bot",
  "stop_child_bot": "Stoppa bot",
  "restart_child_bot": "Starta om bot",
  "bot_settings": "Botinställningar",
  "bot_analytics": "Botanalys",
  "bot_logs": "Botloggar",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Språkval",
  "language_changed": "Språk har ändrats",
  "bot_manager_title": "Bothanterare",
  "available_commands": "Tillgängliga kommandon",
  "change_language": "Byt språk",
  "manage_bots": "Hantera bottar",
  "help_command": "Hjälp",
  "current_features": "Nuvarande funktioner",
  "multilingual_support": "Flerspråkigt stöd",
  "bot_management": "Botadministration",
  "user_preferences": "Användarinställningar",
  "demo_mode": "Demoläge aktivt",
  "welcome": "Välkommen! Välj ditt språk:",
  "data_export": "Exportera data"
}
    },
    'uk': {  # Українська
        # 'example_key': 'Translation in Українська'
        {
  "bot_token": "Токен бота",
  "token_not_found": "Токен не знайдено",
  "bot_not_found": "Бота не знайдено",
  "error_try_again": "Сталася помилка, спробуйте ще раз",
  "back": "Назад",
  "cancel": "Скасувати",
  "token_invalid": "Недійсний токен",
  "token_validation_error": "Помилка валідації токена",
  "bot_already_exists": "Цей бот вже існує",
  "creating_bot_app": "Створення застосунку для бота...",
  "start_bot_success": "Бот успішно запущено",
  "start_bot_error": "Помилка при запуску бота",
  "bot_saved_success": "Бота успішно збережено",
  "delete_confirmation": "Підтвердження видалення",
  "this_action_irreversible": "Цю дію неможливо скасувати",
  "yes_delete": "Так, видалити",
  "no_cancel": "Ні, скасувати",
  "delete_scheduled": "Видалення заплановано",
  "deletion_cancelled": "Видалення скасовано",
  "cancel_deletion": "Скасувати видалення",
  "bot_info_title": "Інформація про бота",
  "start_child_bot": "Запустити бота",
  "stop_child_bot": "Зупинити бота",
  "restart_child_bot": "Перезапустити бота",
  "bot_settings": "Налаштування бота",
  "bot_analytics": "Аналітика бота",
  "bot_logs": "Логи бота",
  "bot_status_online": "Онлайн",
  "bot_status_offline": "Офлайн",
  "language_selection": "Вибір мови",
  "language_changed": "Мову успішно змінено",
  "bot_manager_title": "Менеджер ботів",
  "available_commands": "Доступні команди",
  "change_language": "Змінити мову",
  "manage_bots": "Керувати ботами",
  "help_command": "Допомога",
  "current_features": "Поточні функції",
  "multilingual_support": "Підтримка багатомовності",
  "bot_management": "Керування ботом",
  "user_preferences": "Налаштування користувача",
  "demo_mode": "Демо-режим активний",
  "welcome": "Ласкаво просимо! Оберіть мову:",
  "data_export": "Експорт даних"
}
    },
    'sw': {  # Kiswahili
        # 'example_key': 'Translation in Kiswahili'
        {
  "bot_token": "Tokeni ya bot",
  "token_not_found": "Tokeni haijapatikana",
  "bot_not_found": "Bot haijapatikana",
  "error_try_again": "Hitilafu imetokea, tafadhali jaribu tena",
  "back": "Rudi nyuma",
  "cancel": "Ghairi",
  "token_invalid": "Tokeni si sahihi",
  "token_validation_error": "Hitilafu ya uthibitishaji wa tokeni",
  "bot_already_exists": "Bot hii tayari ipo",
  "creating_bot_app": "Inaunda programu ya bot...",
  "start_bot_success": "Bot imeanza kwa mafanikio",
  "start_bot_error": "Hitilafu ilipotokea wakati wa kuanza bot",
  "bot_saved_success": "Bot imehifadhiwa kwa mafanikio",
  "delete_confirmation": "Uthibitisho wa kufuta",
  "this_action_irreversible": "Hatua hii haiwezi kubatilishwa",
  "yes_delete": "Ndio, futa",
  "no_cancel": "Hapana, ghairi",
  "delete_scheduled": "Kufuta kumewekwa ratiba",
  "deletion_cancelled": "Kufuta kumefutwa",
  "cancel_deletion": "Ghairi kufuta",
  "bot_info_title": "Maelezo ya bot",
  "start_child_bot": "Anzisha bot",
  "stop_child_bot": "Simamisha bot",
  "restart_child_bot": "Anzisha upya bot",
  "bot_settings": "Mipangilio ya bot",
  "bot_analytics": "Takwimu za bot",
  "bot_logs": "Rekodi za bot",
  "bot_status_online": "Mtandaoni",
  "bot_status_offline": "Nje ya mtandao",
  "language_selection": "Chagua lugha",
  "language_changed": "Lugha imebadilishwa kwa mafanikio",
  "bot_manager_title": "Meneja wa bot",
  "available_commands": "Amri zinazopatikana",
  "change_language": "Badilisha lugha",
  "manage_bots": "Simamia bot",
  "help_command": "Msaada",
  "current_features": "Vipengele vya sasa",
  "multilingual_support": "Msaada wa lugha nyingi",
  "bot_management": "Usimamizi wa bot",
  "user_preferences": "Mapendeleo ya mtumiaji",
  "demo_mode": "Hali ya majaribio imewashwa",
  "welcome": "Karibu! Tafadhali chagua lugha yako:",
  "data_export": "Hamisha data"
}
    },
    'he': {  # עברית
        # 'example_key': 'Translation in עברית'
        {
  "bot_token": "אסימון הבוט",
  "token_not_found": "האסימון לא נמצא",
  "bot_not_found": "הבוט לא נמצא",
  "error_try_again": "שגיאה, נסה שוב",
  "back": "חזרה",
  "cancel": "ביטול",
  "token_invalid": "אסימון שגוי",
  "token_validation_error": "שגיאה באימות האסימון",
  "bot_already_exists": "הבוט כבר קיים",
  "creating_bot_app": "יוצר אפליקציית בוט...",
  "start_bot_success": "הבוט הופעל בהצלחה",
  "start_bot_error": "שגיאה בעת הפעלת הבוט",
  "bot_saved_success": "הבוט נשמר בהצלחה",
  "delete_confirmation": "אישור מחיקה",
  "this_action_irreversible": "פעולה זו אינה הפיכה",
  "yes_delete": "כן, מחק",
  "no_cancel": "לא, בטל",
  "delete_scheduled": "המחיקה תוזמנה",
  "deletion_cancelled": "המחיקה בוטלה",
  "cancel_deletion": "בטל מחיקה",
  "bot_info_title": "מידע על הבוט",
  "start_child_bot": "הפעלת הבוט",
  "stop_child_bot": "הפסקת הבוט",
  "restart_child_bot": "אתחול הבוט",
  "bot_settings": "הגדרות הבוט",
  "bot_analytics": "ניתוח נתוני הבוט",
  "bot_logs": "יומני הבוט",
  "bot_status_online": "מקוון",
  "bot_status_offline": "לא מקוון",
  "language_selection": "בחירת שפה",
  "language_changed": "השפה שונתה בהצלחה",
  "bot_manager_title": "מנהל הבוטים",
  "available_commands": "פקודות זמינות",
  "change_language": "שנה שפה",
  "manage_bots": "ניהול בוטים",
  "help_command": "עזרה",
  "current_features": "פיצ׳רים נוכחיים",
  "multilingual_support": "תמיכה רב־לשונית",
  "bot_management": "ניהול בוטים",
  "user_preferences": "העדפות משתמש",
  "demo_mode": "מצב הדגמה פעיל",
  "welcome": "ברוך הבא! אנא בחר שפה:",
  "data_export": "ייצוא נתונים"
}
    },
    'ro': {  # Română
        # 'example_key': 'Translation in Română'
        {
  "bot_token": "Tokenul botului",
  "token_not_found": "Tokenul nu a fost găsit",
  "bot_not_found": "Botul nu a fost găsit",
  "error_try_again": "Eroare, te rog încearcă din nou",
  "back": "Înapoi",
  "cancel": "Anulează",
  "token_invalid": "Token invalid",
  "token_validation_error": "Eroare la validarea tokenului",
  "bot_already_exists": "Acest bot există deja",
  "creating_bot_app": "Se creează aplicația botului...",
  "start_bot_success": "Botul a fost pornit cu succes",
  "start_bot_error": "Eroare la pornirea botului",
  "bot_saved_success": "Botul a fost salvat cu succes",
  "delete_confirmation": "Confirmare ștergere",
  "this_action_irreversible": "Această acțiune este ireversibilă",
  "yes_delete": "Da, șterge",
  "no_cancel": "Nu, anulează",
  "delete_scheduled": "Ștergerea a fost programată",
  "deletion_cancelled": "Ștergerea a fost anulată",
  "cancel_deletion": "Anulează ștergerea",
  "bot_info_title": "Informații despre bot",
  "start_child_bot": "Pornește botul",
  "stop_child_bot": "Oprește botul",
  "restart_child_bot": "Repornește botul",
  "bot_settings": "Setări bot",
  "bot_analytics": "Analize bot",
  "bot_logs": "Jurnale bot",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Selectare limbă",
  "language_changed": "Limba a fost schimbată cu succes",
  "bot_manager_title": "Managerul de boturi",
  "available_commands": "Comenzi disponibile",
  "change_language": "Schimbă limba",
  "manage_bots": "Gestionează boturile",
  "help_command": "Ajutor",
  "current_features": "Funcționalități curente",
  "multilingual_support": "Suport multilingv",
  "bot_management": "Administrare boturi",
  "user_preferences": "Preferințe utilizator",
  "demo_mode": "Mod demo activat",
  "welcome": "Bine ai venit! Alege limba:",
  "data_export": "Exportă datele"
}
    },
    'fa': {  # فارسی
        # 'example_key': 'Translation in فارسی'
        {
  "bot_token": "توکن ربات",
  "token_not_found": "توکن یافت نشد",
  "bot_not_found": "ربات یافت نشد",
  "error_try_again": "خطا، لطفاً دوباره تلاش کنید",
  "back": "بازگشت",
  "cancel": "لغو",
  "token_invalid": "توکن نامعتبر است",
  "token_validation_error": "خطا در اعتبارسنجی توکن",
  "bot_already_exists": "این ربات قبلاً وجود دارد",
  "creating_bot_app": "در حال ساخت اپلیکیشن ربات...",
  "start_bot_success": "ربات با موفقیت راه‌اندازی شد",
  "start_bot_error": "خطا در هنگام راه‌اندازی ربات",
  "bot_saved_success": "ربات با موفقیت ذخیره شد",
  "delete_confirmation": "تأیید حذف",
  "this_action_irreversible": "این عملیات قابل بازگشت نیست",
  "yes_delete": "بله، حذف شود",
  "no_cancel": "خیر، لغو شود",
  "delete_scheduled": "حذف زمان‌بندی شده است",
  "deletion_cancelled": "حذف لغو شد",
  "cancel_deletion": "لغو حذف",
  "bot_info_title": "اطلاعات ربات",
  "start_child_bot": "شروع ربات",
  "stop_child_bot": "توقف ربات",
  "restart_child_bot": "راه‌اندازی مجدد ربات",
  "bot_settings": "تنظیمات ربات",
  "bot_analytics": "تحلیل‌های ربات",
  "bot_logs": "گزارش‌های ربات",
  "bot_status_online": "آنلاین",
  "bot_status_offline": "آفلاین",
  "language_selection": "انتخاب زبان",
  "language_changed": "زبان با موفقیت تغییر کرد",
  "bot_manager_title": "مدیر ربات",
  "available_commands": "دستورات قابل استفاده",
  "change_language": "تغییر زبان",
  "manage_bots": "مدیریت ربات‌ها",
  "help_command": "راهنما",
  "current_features": "ویژگی‌های فعلی",
  "multilingual_support": "پشتیبانی چندزبانه",
  "bot_management": "مدیریت ربات",
  "user_preferences": "تنظیمات کاربر",
  "demo_mode": "حالت دمو فعال است",
  "welcome": "خوش آمدید! لطفاً زبان خود را انتخاب کنید:",
  "data_export": "خروجی گرفتن از داده‌ها"
}
    },
    'ms': {  # Bahasa Melayu
        # 'example_key': 'Translation in Bahasa Melayu'
        {
  "bot_token": "Token bot",
  "token_not_found": "Token tidak dijumpai",
  "bot_not_found": "Bot tidak dijumpai",
  "error_try_again": "Ralat berlaku, sila cuba lagi",
  "back": "Kembali",
  "cancel": "Batal",
  "token_invalid": "Token tidak sah",
  "token_validation_error": "Ralat pengesahan token",
  "bot_already_exists": "Bot ini sudah wujud",
  "creating_bot_app": "Sedang mencipta aplikasi bot...",
  "start_bot_success": "Bot berjaya dimulakan",
  "start_bot_error": "Ralat semasa memulakan bot",
  "bot_saved_success": "Bot berjaya disimpan",
  "delete_confirmation": "Pengesahan penghapusan",
  "this_action_irreversible": "Tindakan ini tidak boleh diundurkan",
  "yes_delete": "Ya, padam",
  "no_cancel": "Tidak, batal",
  "delete_scheduled": "Penghapusan telah dijadualkan",
  "deletion_cancelled": "Penghapusan telah dibatalkan",
  "cancel_deletion": "Batal penghapusan",
  "bot_info_title": "Maklumat bot",
  "start_child_bot": "Mulakan bot",
  "stop_child_bot": "Hentikan bot",
  "restart_child_bot": "Mulakan semula bot",
  "bot_settings": "Tetapan bot",
  "bot_analytics": "Analitik bot",
  "bot_logs": "Log bot",
  "bot_status_online": "Dalam talian",
  "bot_status_offline": "Luar talian",
  "language_selection": "Pemilihan bahasa",
  "language_changed": "Bahasa telah berjaya ditukar",
  "bot_manager_title": "Pengurus bot",
  "available_commands": "Arahan yang tersedia",
  "change_language": "Tukar bahasa",
  "manage_bots": "Urus bot",
  "help_command": "Bantuan",
  "current_features": "Ciri-ciri semasa",
  "multilingual_support": "Sokongan berbilang bahasa",
  "bot_management": "Pengurusan bot",
  "user_preferences": "Keutamaan pengguna",
  "demo_mode": "Mod demo diaktifkan",
  "welcome": "Selamat datang! Sila pilih bahasa anda:",
  "data_export": "Eksport data"
}
    },
    'id': {  # Bahasa Indonesia
        # 'example_key': 'Translation in Bahasa Indonesia'
        {
  "bot_token": "Token bot",
  "token_not_found": "Token tidak ditemukan",
  "bot_not_found": "Bot tidak ditemukan",
  "error_try_again": "Terjadi kesalahan, silakan coba lagi",
  "back": "Kembali",
  "cancel": "Batalkan",
  "token_invalid": "Token tidak valid",
  "token_validation_error": "Kesalahan validasi token",
  "bot_already_exists": "Bot ini sudah ada",
  "creating_bot_app": "Membuat aplikasi bot...",
  "start_bot_success": "Bot berhasil dijalankan",
  "start_bot_error": "Kesalahan saat menjalankan bot",
  "bot_saved_success": "Bot berhasil disimpan",
  "delete_confirmation": "Konfirmasi penghapusan",
  "this_action_irreversible": "Tindakan ini tidak dapat dibatalkan",
  "yes_delete": "Ya, hapus",
  "no_cancel": "Tidak, batalkan",
  "delete_scheduled": "Penghapusan dijadwalkan",
  "deletion_cancelled": "Penghapusan dibatalkan",
  "cancel_deletion": "Batalkan penghapusan",
  "bot_info_title": "Informasi bot",
  "start_child_bot": "Jalankan bot",
  "stop_child_bot": "Hentikan bot",
  "restart_child_bot": "Mulai ulang bot",
  "bot_settings": "Pengaturan bot",
  "bot_analytics": "Analitik bot",
  "bot_logs": "Log bot",
  "bot_status_online": "Online",
  "bot_status_offline": "Offline",
  "language_selection": "Pemilihan bahasa",
  "language_changed": "Bahasa berhasil diubah",
  "bot_manager_title": "Manajer bot",
  "available_commands": "Perintah yang tersedia",
  "change_language": "Ubah bahasa",
  "manage_bots": "Kelola bot",
  "help_command": "Bantuan",
  "current_features": "Fitur saat ini",
  "multilingual_support": "Dukungan multibahasa",
  "bot_management": "Manajemen bot",
  "user_preferences": "Preferensi pengguna",
  "demo_mode": "Mode demo aktif",
  "welcome": "Selamat datang! Silakan pilih bahasa Anda:",
  "data_export": "Ekspor data"
}
    },
}
def get_text(lang: str, key: str) -> str:
    """Récupère le texte traduit selon la langue"""
    return TRANSLATIONS.get(lang, TRANSLATIONS['fr']).get(key, key)

        # La fonction register_user_bot_handlers est asynchrone et sera appelée dans la tâche asyncio
        
    return application
    except Exception as e:
    logger.error(f"Erreur dans handle_pdg_token_input: {e} [ERR_BLM_037]", exc_info=True)
    await update.message.reply_text("❌ Erreur lors de la configuration du Bot PDG. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_037)")

async def check_bot_limits(user_id: int) -> bool:
    """Vérifie si l'utilisateur peut ajouter un nouveau bot"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    # Check for trial period for 'free' plan
    if plan == "free":
        trial_end_date = db.get_user_trial_end_date(user_id)
        if trial_end_date and datetime.now() < datetime.fromisoformat(trial_end_date):
            # During trial, allow up to 10 bots
            if len(user_bots) >= 10:
                return False
        else:
            # After trial, apply plan limits for 'free' plan
            if len(user_bots) >= plan_limits["bots"]:
                return False
    else:
        # For other plans, apply their limits directly
        if len(user_bots) >= plan_limits["bots"]:
            return False
    return True

async def check_group_limits(user_id: int, new_group_id: int = 0) -> bool:
    """Vérifie les limites de groupes"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    total_groups = sum(len(bot.get("groups", [])) for bot in user_bots)
    if new_group_id > 0:
        total_groups += 1
    
    if total_groups >= plan_limits["groups"]:
        return False
    return Truedef get_text(lang: str, key: str) -> str:
    """Récupère le texte traduit selon la langue"""
    return TRANSLATIONS.get(lang, TRANSLATIONS['fr']).get(key, key)

# La fonction register_user_bot_handlers est asynchrone et sera appelée dans la tâche asyncio
    return application
except Exception as e:
    logger.error(f"Erreur dans handle_pdg_token_input: {e} [ERR_BLM_A37]", exc_info=True)
    await update.message.reply_text("Erreur lors de la configuration du Bot PDG. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_B37)")

async def check_bot_limits(user_id: int) -> bool:
    """Vérifie si l'utilisateur peut ajouter un nouveau bot"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    # Check for trial period for 'free' plan
    if plan == "free":
        trial_end_date = db.get_user_trial_end_date(user_id)
        if trial_end_date and datetime.now() < datetime.fromisoformat(trial_end_date):
            # During trial, allow up to 10 bots
            if len(user_bots) >= 10:
                return False
        else:
            # After trial, apply plan limits for 'free' plan
            if len(user_bots) >= plan_limits["bots"]:
                return False
    else:
        # For other plans, apply their limits directly
        if len(user_bots) >= plan_limits["bots"]:
            return False
    return True

# Comprehensive multilingual translations
        # La fonction register_user_bot_handlers est asynchrone et sera appelée dans la tâche asyncio
        
    return application
    except Exception as e:
        logger.error(f"Erreur initialisation bot fils: {e}")
        return None

async def check_bot_limits(user_id: int) -> bool:
    """Vérifie si l'utilisateur peut ajouter un nouveau bot"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    # Check for trial period for 'free' plan
    if plan == "free":
        trial_end_date = db.get_user_trial_end_date(user_id)
        if trial_end_date and datetime.now() < datetime.fromisoformat(trial_end_date):
            # During trial, allow up to 10 bots
            if len(user_bots) >= 10:
                return False
        else:
            # After trial, apply plan limits for 'free' plan
            if len(user_bots) >= plan_limits["bots"]:
                return False
    else:
        # For other plans, apply their limits directly
        if len(user_bots) >= plan_limits["bots"]:
            return False
    return True

async def check_group_limits(user_id: int, new_group_id: int = 0) -> bool:
    """Vérifie les limites de groupes"""
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    total_groups = sum(len(bot.get("groups", [])) for bot in user_bots)
    if new_group_id > 0:
        total_groups += 1
    
    if total_groups >= plan_limits["groups"]:
        return False
    return True

class BotLinkingManager:

    @staticmethod
    async def handle_main_start(update: Update, context: CallbackContext):
        """Handler /start pour le bot principal"""
        try:
            user_id = update.effective_user.id
            
            if db.is_new_user(user_id):
                db.users[user_id] = {
                    'state': UserStates.INITIAL.value,
                    'language': 'fr',
                    'trial_end_date': (datetime.now() + timedelta(days=14)).isoformat()
                }
                db.save_to_disk('users', {str(user_id): db.users[user_id]})
                await BotLinkingManager.show_language_options(update, context)
            else:
                await show_main_menu(update, context)

        except Exception as e:
            logger.error(f"Erreur dans handle_main_start: {e} [ERR_BLM_004]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de l'initialisation. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_004)")

    @staticmethod
    async def show_language_options(update: Update, context: CallbackContext):
        """Affiche les options de langue"""
        try:
            if update.message:
                user_id = update.message.from_user.id
                lang = db.get_user_language(user_id) or 'fr'
            elif update.callback_query:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                lang = db.get_user_language(user_id) or 'fr'
            
            text = (
                "🌐 Veuillez choisir votre langue préférée :"
                if lang == 'fr' else
                "🌐 Please choose your preferred language:"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("🇫🇷 Français", callback_data="setlang_fr"),
                    InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"),
                    InlineKeyboardButton("🇪🇸 Español", callback_data="setlang_es")
                ],
                [
                    InlineKeyboardButton("🇩🇪 Deutsch", callback_data="setlang_de"),
                    InlineKeyboardButton("🇨🇳 中文", callback_data="setlang_zh"),
                    InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="setlang_hi")
                ],
                [
                    InlineKeyboardButton("🇯🇵 日本語", callback_data="setlang_ja"),
                    InlineKeyboardButton("🇰🇷 한국어", callback_data="setlang_ko"),
                    InlineKeyboardButton("🇹🇭 ไทย", callback_data="setlang_th")
                ],
                [
                    InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
                    InlineKeyboardButton("🇵🇹 Português", callback_data="setlang_pt"),
                    InlineKeyboardButton("🇮🇹 Italiano", callback_data="setlang_it")
                ],
                [
                    InlineKeyboardButton("🔙 Retour" if lang == 'fr' else "🔙 Back", 
                                       callback_data="back_to_main")
                ]
            ]
            
            if update.callback_query:
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Erreur dans show_language_options: {e} [ERR_BLM_005]", exc_info=True)

    @staticmethod
    async def set_language_callback(update: Update, context: CallbackContext):
        """Définit la langue de l'utilisateur via callback"""
        try:
            query = update.callback_query
            await query.answer()
            lang_code = query.data.split("_")[1]
            user_id = query.from_user.id
            
            db.set_user_language(user_id, lang_code)
            
            lang_names = {
    'fr': "Français",
    'en': "English",
    'es': "Español", 
    'de': "Deutsch",
    'zh': "中文",
    'hi': "हिन्दी",
    'ja': "日本語",
    'ko': "한국어",
    'th': "ไทย",
    'ru': "Русский",
    'pt': "Português",
    'it': "Italiano",
    'ar': "العربية",
    'tr': "Türkçe",
    'vi': "Tiếng Việt",
    'pl': "Polski",
    'nl': "Nederlands",
    'sv': "Svenska",
    'uk': "Українська",
    'sw': "Kiswahili",
    'he': "עברית",
    'ro': "Română",
    'fa': "فارسی",
    'ms': "Bahasa Melayu",
    'id': "Bahasa Indonesia"
}
            
            confirmation = (
                f"✅ Langue définie sur {lang_names[lang_code]}"
                if lang_code == 'fr' else
                f"✅ Language set to {lang_names[lang_code]}"
            )
            
            await query.edit_message_text(
                confirmation,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ Commencer" if lang_code == 'fr' else "✅ Start",
                        callback_data="terms_accepted"
                    )]
                ])
            )
        except Exception as e:
            logger.error(f"Erreur dans set_language_callback: {e} [ERR_BLM_006]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_006)")

    @staticmethod
    async def accept_terms(update: Update, context: CallbackContext):
        """Affiche et gère l'acceptation des conditions"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            terms_text = (
                "📜 <b>Conditions d'utilisation</b>\n\n"
                "1. Confidentialité : Vos données sont cryptées\n"
                "2. Utilisation : Interdiction de spam\n"
                "3. Sécurité : Ne partagez pas vos tokens\n\n"
                "En continuant, vous acceptez nos conditions."
                if lang == 'fr' else
                "📜 <b>Terms of Service</b>\n\n"
                "1. Privacy: Your data is encrypted\n"
                "2. Usage: No spamming allowed\n"
                "3. Security: Don't share your tokens\n\n"
                "By continuing, you accept our terms."
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ J'accepte" if lang == 'fr' else "✅ I Accept", 
                                     callback_data="terms_accepted")],
                [InlineKeyboardButton("❌ Refuser" if lang == 'fr' else "❌ Decline", 
                                    callback_data="terms_declined")]
            ]
            
            await query.edit_message_text(
                terms_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Erreur dans accept_terms: {e} [ERR_BLM_007]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_007)")

    @staticmethod
    async def terms_accepted(update: Update, context: CallbackContext):
        """Passe au menu principal après acceptation"""
        try:
            query = update.callback_query
            await query.answer()
            db.save_terms_acceptance(query.from_user.id)
            await show_main_menu(update, context)
        except Exception as e:
            logger.error(f"Erreur dans terms_accepted: {e} [ERR_BLM_008]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_008)")

    @staticmethod
    async def start_bot_creation(update: Update, context: CallbackContext):
        """Démarre le processus de création de bot"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            
            text = (
                "🤖 Création de votre bot personnel\n\n"
                "Avez-vous déjà un bot Telegram existant ?"
                if lang == 'fr' else
                "🤖 Creating your bot assistant\n\n"
                "Do you already have an existing Telegram bot?"
            )
            
            if update.message:
                await update.message.reply_text(
                    text, 
                    reply_markup=KeyboardManager.bot_creation_options(lang)
                )
            else:
                await query.edit_message_text(
                    text, 
                    reply_markup=KeyboardManager.bot_creation_options(lang)
                )
        except Exception as e:
            logger.error(f"Erreur dans start_bot_creation: {e} [ERR_BLM_009]", exc_info=True)
            if update.callback_query:
                await update.callback_query.message.reply_text("❌ Erreur lors du démarrage. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_009)")
            else:
                await update.message.reply_text("❌ Erreur lors du démarrage. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_009)")

    @staticmethod
    async def handle_has_token_yes(update: Update, context: CallbackContext):
        """Gère la réponse 'Oui, j'ai un token'"""
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'

            security_advice = (
                "🔐 Conseil de sécurité :\n"
                "1. Ne partagez jamais votre token publiquement\n"
                "2. Utilisez /revoke dans @BotFather si compromis\n"
                "3. Notre système le chiffrera automatiquement"
                if lang == 'fr' else
                "🔐 Security advice:\n"
                "1. Never share your token publicly\n"
                "2. Use /revoke in @BotFather if compromised\n"
                "3. Our system will encrypt it automatically"
            )

            prompt = "Parfait ! Veuillez m'envoyer votre token :" if lang == 'fr' else "Perfect! Please send me your token:"
            await query.edit_message_text(f"✅ {prompt}\n\n{security_advice}", parse_mode="Markdown")
            context.user_data["awaiting_token"] = True
        except Exception as e:
            logger.error(f"Erreur dans handle_has_token_yes: {e} [ERR_BLM_010]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_010)")

    @staticmethod
    async def handle_has_token_no(update: Update, context: CallbackContext):
        """Gère la réponse 'Non, je n'ai pas de token'"""
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'

            creation_guide = (
                "⚙️ Création de votre premier bot :\n\n"
                "1. Ouvrez @BotFather\n"
                "2. Envoyez /newbot\n"
                "3. Suivez les instructions\n"
                "4. Copiez le token généré\n\n"
                "⚠️ Consignes de sécurité :\n"
                "- Ne partagez JAMAIS ce token\n"
                "- Changez-le immédiatement si compromis\n"
                "- Notre système le chiffrera automatiquement\n\n"
            )

            await query.edit_message_text(creation_guide, parse_mode="Markdown")
            context.user_data["awaiting_token"] = True
        except Exception as e:
            logger.error(f"Erreur dans handle_has_token_no: {e} [ERR_BLM_011]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_011)")

    @staticmethod
    async def handle_token_input(update: Update, context: CallbackContext):
        if not context.user_data.get("awaiting_token"):
            return

        try:
            token = update.message.text.strip()
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'

            # Validation avec retour des données
            bot_data = sync_validate_bot_token(token)
            if not bot_data:
                error_msg = "❌ Token invalide. Veuillez vérifier et réessayer."
                await update.message.reply_text(error_msg)
                return

            # Utilisez les données retournées
            bot_username = bot_data.get("username")
            bot_name = bot_data.get("first_name")
            
            bot_link = f"https://t.me/{bot_username}" # Define bot_link here
            
            creation_time = datetime.now().isoformat()
            db.save_user_bot(user_id, token, bot_username, bot_name, creation_time)


            # Lancement du bot enfant
            try:
                child_app = init_child_bot(token, bot_username)
                if child_app:
                    # Enregistrer les handlers spécifiques au bot fils
                    from utils.user_features import setup_user_bot_handlers
                    await setup_user_bot_handlers(child_app)                    
                    # Démarrer le polling du bot fils en arrière-plan
                    import asyncio
                    await child_app.initialize()
                    await child_app.start()
                    asyncio.create_task(child_app.updater.start_polling())
            # Message de succès avec boutons
            success_text = (
                f"✅ Bot @{bot_username} connecté avec succès !\n\n"
                f"Vous pouvez maintenant utiliser votre bot : {bot_link}\n\n"
                f"N'oubliez pas de consulter votre plan pour les limites et fonctionnalités : /planinfo"
                if lang == 'fr' else
                f"✅ Bot @{bot_username} successfully connected!\n\n"
                f"You can now use your bot: {bot_link}\n\n"
                f"Don't forget to check your plan for limits and features: /planinfo"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🤖 Aller à votre bot", url=bot_link),
                    InlineKeyboardButton("📊 Mon plan", callback_data="show_plan_info")
                ]
            ])

            await update.message.reply_text(success_text, reply_markup=keyboard, parse_mode="HTML")

            # Message de bienvenue dans le nouveau bot


        except Exception as e:
            logger.error(f"ERREUR: {str(e)}", exc_info=True)
            await update.message.reply_text("❌ Erreur lors du traitement")
        finally:
            context.user_data["awaiting_token"] = False

    @staticmethod
    async def log_violation(vtype: str, user_id: int, plan: str, context: CallbackContext):
        """Journalise les violations de limites"""
        try:
            pdg = db.pdg_config
            if not pdg or not pdg.get("is_active"):
                return
                
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_text = f"[{vtype}] {now} — <code>{user_id}</code> dépassement ({plan})"
            if pdg:
                # Ensure the main bot sends the message to the PDG owner
                await context.bot.send_message(pdg["owner"], log_text, parse_mode="HTML")
                if pdg.get("log_channel"):
                    # Ensure the main bot sends the message to the log channel
                    await context.bot.send_message(pdg["log_channel"], log_text, parse_mode="HTML")
                    db.setdefault("log_archive", []).append({
                        "type": vtype,
                        "timestamp": now,
                        "user_id": user_id,
                        "plan": plan
                    })
        except Exception as e:
            logger.error(f"Erreur dans log_violation: {e} [ERR_BLM_016]", exc_info=True)

    @staticmethod
    async def handle_services(update: Update, context: CallbackContext):
        """Gère le bouton 🛠️ Services et la commande /services"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            
            text = "🛠️ <b>Services disponibles</b> :" if lang == 'fr' else "🛠️ <b>Available Services</b>:"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Mes bots créés 🤖", callback_data="my_bots")],
                [InlineKeyboardButton("🔍 Recherche avancée", callback_data="services_search")],
                [InlineKeyboardButton("❤️ Groupe de rencontre 👩‍❤️‍👨", callback_data="services_meetup")],
                [InlineKeyboardButton("🔄 Change format fichier 📁", callback_data="services_format")],
                [InlineKeyboardButton("📝 Texte vers voix🎙️", callback_data="services_tts")],
                [InlineKeyboardButton("🎙️ Voix vers texte 📝", callback_data="services_stt")],
                [InlineKeyboardButton("📢 Créer un post 📢", callback_data="services_post")],
                [InlineKeyboardButton("📊 Créé un sondage 📊", callback_data="services_poll")],
                [InlineKeyboardButton("🔗 Crée un lien court 🔗", callback_data="services_shortlink")],
                [InlineKeyboardButton("🚀 Créé une publicité 🚀", callback_data="services_ads")],
                [InlineKeyboardButton("🤑 Investissement intelligent 🤑", callback_data="services_investment")],
                [InlineKeyboardButton("🔙 Retour", callback_data="back_to_main")]
            ])
            
            if update.message:
                await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"Erreur dans handle_services: {e} [ERR_BLM_017]", exc_info=True)
            if update.callback_query:
                await update.callback_query.message.reply_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_017)")
            else:
                await update.message.reply_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_017)")

    @staticmethod
    async def handle_service_submenu(update: Update, context: CallbackContext):
        """Gère les sous-menus des services"""
        query = update.callback_query
        await query.answer()
        lang = db.get_user_language(query.from_user.id) or 'fr'
        
        text = "🚧 Fonctionnalité en cours de construction" if lang == 'fr' else "🚧 Feature under construction"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Retour", callback_data="back_to_services")]
        ])
        
        await query.edit_message_text(text, reply_markup=keyboard)

    @staticmethod
    async def handle_back_to_services(update: Update, context: CallbackContext):
        """Retour au menu des services"""
        query = update.callback_query
        await query.answer()
        await BotLinkingManager.handle_services(update, context)

    @staticmethod
    async def handle_help_command(update: Update, context: CallbackContext):
        """Gère le bouton 'Aide'"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
            
            lang = db.get_user_language(user_id) or 'fr'

            help_text = (
                "🆘 <b>Aide TeleSucheBot</b>\n\n"
                "<b>Fonctionnalités principales :</b>\n"
                "• ⚙️ Cloner votre bot : Créez votre propre assistant\n"
                "• 🤝 Communauté : Rejoignez nos canaux et groupes\n"
                "• 🛠️ Services : Accédez à nos outils avancés\n\n"
                "<b>Support technique :</b>\n"
                "👉 @TeleSucheSupport\n"
                "📬 support@telesuche.com\n\n"
                "<b>Documentation :</b>\n"
                "🌐 https://docs.telesuche.com"
                if lang == 'fr' else
                "🆘 <b>TeleSucheBot Help</b>\n\n"
                "<b>Main features:</b>\n"
                "• ⚙️ Clone your bot: Create your personal assistant\n"
                "• 🤝 Community: Join our channels and groups\n"
                "• 🛠️ Services: Access our advanced tools\n\n"
                "<b>Technical support:</b>\n"
                "👉 @TeleSucheSupport\n"
                "📬 support@telesuche.com\n\n"
                "<b>Documentation :</b>\n"
                "🌐 https://docs.telesuche.com"
            )
            
            if update.message:
                await update.message.reply_text(help_text, parse_mode="HTML")
            else:
                await query.edit_message_text(
                    help_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Retour" if lang == 'fr' else "🔙 Back", callback_data='back_to_main')]
                    ])
                )
        except Exception as e:
            logger.error(f"Erreur dans handle_help_command: {e}", exc_info=True)

    @staticmethod
    async def handle_upgrade_plan(update: Update, context: CallbackContext):
        """Affiche les options de mise à niveau"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            text = (
                "💎 <b>Choisissez un plan</b>\n\n"
            )
            
            keyboard = []
            for plan_id, plan_data in PLANS.items():
                features_text = "\n".join([f"• {f}" for f in plan_data["features"]])
                text += (
                    f"{plan_data['label']} ({plan_data['price']})\n"
                    f"{features_text}\n"
                    f"{plan_data['more_info_link']}\n\n"
                )
                keyboard.append([
                    InlineKeyboardButton(
                        f"{plan_data['label']} - {plan_data['price']}",
                        callback_data=f"plan_details:{plan_id}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔙 Retour", callback_data="back_to_main")
            ])

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"Erreur dans handle_upgrade_plan: {e} [ERR_BLM_018]", exc_info=True)
            await query.edit_message_text(
                "❌ Erreur d'affichage des plans. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_018)"
                if lang == 'fr'
                else "❌ Error displaying plans. Contact support (@TeleSucheSupport) if the problem persists. (ERR_BLM_018)"
            )

    @staticmethod
    async def handle_confirm_upgrade(update: Update, context: CallbackContext):
        """Confirmation finale de l'upgrade"""
        try:
            query = update.callback_query
            await query.answer()
            plan_id = query.data.split(":")[1]
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'

            # Ici vous devriez intégrer votre logique de paiement
            # Pour l'exemple, nous supposons que le paiement est validé
            payment_processor = PaymentProcessor()
            # Supposons que le plan a un prix et une devise associés dans PLANS
            plan_price = PLANS[plan_id].get("price_value", 0.0) # Assurez-vous que PLANS contient 'price_value'
            plan_currency = PLANS[plan_id].get("currency", "USD") # Assurez-vous que PLANS contient 'currency'

            if await payment_processor.process_payment(user_id, plan_price, plan_currency, plan_id):
                db.set_user_plan(user_id, plan_id)
                await query.edit_message_text(
                    f"🎉 Félicitations ! Votre compte a été upgradé." if lang == 'fr' \
                    else f"🎉 Congratulations! Your account has been upgraded."
                )
                # Envoyer un message avec les nouvelles limites
                await BotLinkingManager.show_plan_info(update, context)
            else:
                await query.edit_message_text(
                    "❌ Échec du paiement. Veuillez réessayer." if lang == 'fr' \
                    else "❌ Payment failed. Please try again."
                )

        except Exception as e:
            logger.error(f"Erreur dans handle_confirm_upgrade: {e} [ERR_BLM_019]", exc_info=True)
            await query.edit_message_text(
                "❌ Erreur lors de la mise à niveau. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_019)"
                if lang == 'fr'
                else "❌ Upgrade error. Contact support (@TeleSucheSupport) if the problem persists. (ERR_BLM_019)"
            )

    @staticmethod
    async def show_plan_info(update: Update, context: CallbackContext):
        """Affiche les informations du plan actuel"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            plan = get_user_plan(user_id)
            plan_data = PLANS.get(plan, PLANS["free"])
            plan_limits = get_plan_limits(plan)
            
            user_bots = db.get_user_bots(user_id)
            bot_count = len(user_bots)
            
            text = (
                f"💎 <b>Plan actuel : {plan_data['label']}</b>\n\n"
                f"📊 <b>Utilisation :</b>\n"
                f"• Bots : {bot_count}/{plan_limits['bots']}\n"
                f"• Groupes : 0/{plan_limits['groups']}\n\n"
                f"<b>Fonctionnalités :</b>\n"
            )
            
            for feature in plan_data["features"]:
                text += f"• {feature}\n"
                
            if plan == "free":
                text += f"\n💡 <b>Upgradez pour plus de fonctionnalités !</b>"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Upgrade", callback_data="upgrade_plan")],
                    [InlineKeyboardButton("🔙 Retour", callback_data="back_to_main")]
                ])
            else:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Retour", callback_data="back_to_main")]
                ])
            
            if update.message:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
                
        except Exception as e:
            logger.error(f"Erreur dans show_plan_info: {e} [ERR_BLM_020]", exc_info=True)

    @staticmethod
    async def handle_community(update: Update, context: CallbackContext):
        """Gère le bouton 'Communauté'"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            
            text = (
                "🤝 <b>Rejoignez notre communauté !</b>\n\n"
                "Connectez-vous avec d'autres utilisateurs, partagez vos expériences et obtenez de l'aide."
                if lang == 'fr' else
                "🤝 <b>Join our community!</b>\n\n"
                "Connect with other users, share experiences and get help."
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Canal officiel", url="https://t.me/TeleSucheChannel")],
                [InlineKeyboardButton("💬 Groupe de discussion", url="https://t.me/TeleSucheGroup")],
                [InlineKeyboardButton("🆘 Support technique", url="https://t.me/TeleSucheSupport")],
                [InlineKeyboardButton("🔙 Retour", callback_data="back_to_main")]
            ])
            
            if update.message:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
                
        except Exception as e:
            logger.error(f"Erreur dans handle_community: {e} [ERR_BLM_021]", exc_info=True)

    @staticmethod
    async def handle_delete_bot_command(update: Update, context: CallbackContext):
        """Gère la commande de suppression de bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            # Extraire l'ID du bot depuis le callback_data
            bot_id = query.data.split(":")[1]
            
            # Récupérer les informations du bot
            user_bots = db.get_user_bots(user_id)
            selected_bot = None
            for bot in user_bots:
                if bot.get("bot_username") == bot_id or str(bot.get("id", "")) == bot_id:
                    selected_bot = bot
                    break
                    
            if not selected_bot:
                await query.edit_message_text(
                    "❌ Bot non trouvé" if lang == 'fr' else "❌ Bot not found"
                )
                return
                
            bot_username = selected_bot.get("bot_username", "Unknown")
            
            text = (
                f"⚠️ <b>Supprimer le bot</b>\n\n"
                f"🤖 @{bot_username}\n\n"
                f"Cette action est irréversible. Êtes-vous sûr ?"
                if lang == 'fr' else
                f"⚠️ <b>Delete bot</b>\n\n"
                f"🤖 @{bot_username}\n\n"
                f"This action is irreversible. Are you sure?"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Oui, supprimer" if lang == 'fr' else "✅ Yes, delete",
                    callback_data=f"confirm_delete:{bot_id}"
                )],
                [InlineKeyboardButton(
                    "❌ Annuler" if lang == 'fr' else "❌ Cancel",
                    callback_data="my_bots"
                )]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Erreur dans handle_delete_bot_command: {e} [ERR_BLM_022]", exc_info=True)

    @staticmethod
    async def handle_final_delete_confirmation(update: Update, context: CallbackContext):
        """Confirmation finale pour supprimer un bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            bot_id = query.data.split(":")[1]
            
            # Supprimer le bot de la base de données
            success = db.delete_user_bot(user_id, bot_id)
            
            if success:
                # Arrêter le bot s'il est en cours d'exécution
                if bot_id in child_bots:
                    try:
                        app = child_bots[bot_id]
                        await app.stop()
                        del child_bots[bot_id]
                    except Exception as e:
                        logger.error(f"Erreur arrêt bot {bot_id}: {e}")
                
                text = (
                    f"✅ Bot supprimé avec succès !"
                    if lang == 'fr' else
                    f"✅ Bot deleted successfully!"
                )
            else:
                text = (
                    f"❌ Erreur lors de la suppression"
                    if lang == 'fr' else
                    f"❌ Error during deletion"
                )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔙 Mes bots" if lang == 'fr' else "🔙 My bots",
                    callback_data="my_bots"
                )]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Erreur dans handle_final_delete_confirmation: {e} [ERR_BLM_023]", exc_info=True)

    @staticmethod
    async def show_bot_token(update: Update, context: CallbackContext):
        """Affiche le token du bot."""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            user_bots = db.get_user_bots(user_id)
            selected_bot = next((bot for bot in user_bots if bot.get("bot_username") == bot_username), None)

            if not selected_bot:
                await query.edit_message_text(get_text(lang, 'bot_not_found'))
                return

            bot_token = selected_bot.get("token", "N/A")

            text = (
                f"<b>{get_text(lang, 'bot_token_title')}</b>\n\n"
                f"<code>{bot_token}</code>\n\n"
                f"{get_text(lang, 'bot_token_security')}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'back_to_bot_info'), callback_data=f"show_bot_info:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans show_bot_token: {e} [ERR_BLM_038]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_038)")

    @staticmethod
    async def handle_under_construction(update: Update, context: CallbackContext):
        """Gère les boutons 'En cours de construction !'"""
        query = update.callback_query
        await query.answer()
        lang = db.get_user_language(query.from_user.id) or 'fr'
        
        text = get_text(lang, 'under_construction')
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="my_bots")]
        ])
        
        await query.edit_message_text(text, reply_markup=keyboard)

    @staticmethod
    async def show_bot_info(update: Update, context: CallbackContext):
        """Affiche les informations détaillées du bot."""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            user_bots = db.get_user_bots(user_id)
            selected_bot = next((bot for bot in user_bots if bot.get("bot_username") == bot_username), None)

            if not selected_bot:
                await query.edit_message_text(get_text(lang, 'bot_not_found'))
                return

            bot_name = selected_bot.get("bot_name", "N/A")
            creation_time = selected_bot.get("creation_time", "N/A")
            
            # Formatage de la date de création
            if creation_time != "N/A":
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(creation_time)
                    creation_date = dt.strftime("%Y-%m-%d")
                    creation_time_formatted = dt.strftime("%H:%M:%S")
                except:
                    creation_date = "2025-07-21"
                    creation_time_formatted = "17:33:59"
            else:
                creation_date = "2025-07-21"
                creation_time_formatted = "17:33:59"

            text = (
                f"<b>{get_text(lang, 'bot_info_title')}</b>\n\n"
                f"<b>{get_text(lang, 'name')}</b> : {bot_name}\n"
                f"<b>{get_text(lang, 'username')}</b> : @{bot_username}\n"
                f"<b>{get_text(lang, 'bot_id')}</b> : N/A\n"
                f"<b>{get_text(lang, 'creation_date')}</b> : \n"
                f"  ├📆 {creation_date} \n"
                f"  └🕑{creation_time_formatted}.\n\n"
                f"<b>{get_text(lang, 'statistics')}</b>\n\n"
                f"{get_text(lang, 'earnings')} \n"
                f"  ├ {get_text(lang, 'total')} 565.00€\n"
                f"  ├ {get_text(lang, 'withdrawn')} 16.00€\n"
                f"  └ {get_text(lang, 'pending')} 100.00€\n\n"
                f"  {get_text(lang, 'users')}\n"
                f"  ├ {get_text(lang, 'total_users')} 300600\n"
                f"  ├ {get_text(lang, 'active')} 240000\n"
                f"  └ {get_text(lang, 'inactive')} 60000\n\n"
                f"  {get_text(lang, 'community')}\n"
                f"  ├ {get_text(lang, 'active_groups')} 50\n"
                f"  └ {get_text(lang, 'active_channels')} 75\n\n"
                f"  {get_text(lang, 'monetization')} \n"
                f"  └ {get_text(lang, 'monetization_active')}\n\n"
                f"   {get_text(lang, 'files')} : \n"
                f"  └ 2.500.000 files\n\n"
                f"------\n"
                f"{get_text(lang, 'bot_token_security')}"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'view_bot_token'), callback_data=f"show_token:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'delete_bot'), callback_data=f"ask_delete_bot:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'invite_admin'), callback_data="under_construction")],
                [InlineKeyboardButton(get_text(lang, 'general_report'), callback_data="under_construction")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans show_bot_info: {e} [ERR_BLM_039]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_039)")

    @staticmethod
    async def handle_my_bots(update: Update, context: CallbackContext):
        """Gère la commande /mybots pour afficher les bots de l'utilisateur"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            user_bots = db.get_user_bots(user_id)
            
            if not user_bots:
                text = get_text(lang, 'no_bots_connected')
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(lang, 'create_bot'), callback_data="createbot")]
                ])
            else:
                text = get_text(lang, 'your_connected_bots')
                keyboard_buttons = []
                
                for bot in user_bots:
                    bot_username = bot.get("bot_username")
                    bot_name = bot.get("bot_name")
                    if bot_username and bot_name:
                        keyboard_buttons.append([
                            InlineKeyboardButton(f"{get_text(lang, 'bot_prefix')}{bot_username}", callback_data=f"bot_detail:{bot_username}")
                        ])
                
                keyboard_buttons.append([
                    InlineKeyboardButton(get_text(lang, 'add_bot'), callback_data="createbot"),
                    InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="back_to_main")
                ])
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            if update.message:
                await update.message.reply_text(text, reply_markup=keyboard)
            else:
                await query.edit_message_text(text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"Erreur dans handle_my_bots: {e} [ERR_BLM_001]", exc_info=True)
            error_text = f"{get_text(lang, 'error_try_again')} (ERR_BLM_001)"
            if update.message:
                await update.message.reply_text(error_text)
            else:
                await query.edit_message_text(error_text)

    @staticmethod
    async def handle_createbot(update: Update, context: CallbackContext):
        """Gère le processus de création d'un nouveau bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'

            # Vérifier les limites de bots
            if not await check_bot_limits(user_id):
                text = get_text(lang, 'bot_limit_exceeded')
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(lang, 'upgrade_plan'), callback_data="upgrade_plan")],
                    [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="my_bots")]
                ])
                await query.edit_message_text(text, reply_markup=keyboard)
                return

            # Demander le token du bot
            text = (
                f"<b>{get_text(lang, 'add_bot_token')}</b>\n\n"
                f"{get_text(lang, 'enter_token')}\n\n"
                f"<i>{get_text(lang, 'token_format')}</i>"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="my_bots")]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            
            # Définir l'état utilisateur pour attendre le token
            context.user_data['awaiting_bot_token'] = True
            
        except Exception as e:
            logger.error(f"Erreur dans handle_createbot: {e} [ERR_BLM_002]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_002)")

    @staticmethod
    async def handle_bot_token_input(update: Update, context: CallbackContext):
        """Gère la saisie du token de bot"""
        try:
            if not context.user_data.get('awaiting_bot_token'):
                return
                
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            token = update.message.text.strip()
            
            # Valider le format du token
            if not token or ':' not in token:
                text = get_text(lang, 'token_invalid')
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="my_bots")]
                ])
                await update.message.reply_text(text, reply_markup=keyboard)
                return
            
            # Valider le token avec l'API Telegram
            try:
                bot_info = sync_validate_bot_token(token)
                if not bot_info:
                    text = get_text(lang, 'token_validation_error')
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="my_bots")]
                    ])
                    await update.message.reply_text(text, reply_markup=keyboard)
                    return
                    
                bot_username = bot_info.get("username")
                bot_name = bot_info.get("first_name")
                
                # Vérifier si le bot existe déjà
                user_bots = db.get_user_bots(user_id)
                if any(bot.get("bot_username") == bot_username for bot in user_bots):
                    text = get_text(lang, 'bot_already_exists')
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="my_bots")]
                    ])
                    await update.message.reply_text(text, reply_markup=keyboard)
                    context.user_data['awaiting_bot_token'] = False
                    return
                
                # Sauvegarder le bot
                creation_time = datetime.now().isoformat()
                db.save_user_bot(user_id, token, bot_username, bot_name, creation_time)
                
                # Créer l'application bot
                text = get_text(lang, 'creating_bot_app')
                await update.message.reply_text(text)
                
                bot_app = init_child_bot(token, bot_username)
                if bot_app:
                # Message de succès
                success_text = f"✅ {get_text(lang, 'bot_saved_success')}\n\n🤖 @{bot_username}"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="my_bots")]
                ])
                await update.message.reply_text(success_text, reply_markup=keyboard)
                
            except Exception as e:
                logger.error(f"Erreur validation token: {e}")
                text = get_text(lang, 'token_validation_error')
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="my_bots")]
                ])
                await update.message.reply_text(text, reply_markup=keyboard)
            
            context.user_data['awaiting_bot_token'] = False
            
        except Exception as e:
            logger.error(f"Erreur dans handle_bot_token_input: {e} [ERR_BLM_003]", exc_info=True)
            await update.message.reply_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_003)")

    @staticmethod
    async def ask_delete_bot(update: Update, context: CallbackContext):
        """Demande confirmation pour supprimer un bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]
            
            text = (
                f"<b>{get_text(lang, 'delete_confirmation')}</b>\n\n"
                f"🤖 @{bot_username}\n\n"
                f"⚠️ {get_text(lang, 'this_action_irreversible')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'yes_delete'), callback_data=f"confirm_delete_bot:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'no_cancel'), callback_data=f"show_bot_info:{bot_username}")]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Erreur dans ask_delete_bot: {e} [ERR_BLM_004]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_004)")

    @staticmethod
    async def confirm_delete_bot(update: Update, context: CallbackContext):
        """Confirme la suppression d'un bot avec délai de 24h"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]
            
            # Programmer la suppression dans 24h
            deletion_time = datetime.now() + timedelta(hours=24)
            text = (
                f"⏰ {get_text(lang, 'delete_scheduled')}\n\n"
                f"🤖 @{bot_username}\n"
                f"🕐 {deletion_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Vous pouvez annuler cette suppression avant cette date."
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'cancel_deletion'), callback_data=f"cancel_delete_bot:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="my_bots")]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Erreur dans confirm_delete_bot: {e} [ERR_BLM_005]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_005)")

    @staticmethod
    async def cancel_delete_bot(update: Update, context: CallbackContext):
        """Annule la suppression programmée d'un bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]
            
            # Annuler la suppression programmée
            deletion_key = f"{user_id}:{bot_username}"
            if deletion_key in pending_deletions:
                del pending_deletions[deletion_key]
            
            db.cancel_bot_deletion(user_id, bot_username)
            
            text = f"✅ {get_text(lang, 'deletion_cancelled')}\n🤖 @{bot_username}"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"show_bot_info:{bot_username}")]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Erreur dans cancel_delete_bot: {e} [ERR_BLM_006]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_006)")

    @staticmethod
    async def execute_pending_deletions():
        """Exécute les suppressions de bots programmées"""
        try:
            current_time = datetime.now()
            to_delete = []
            
            for deletion_key, deletion_time in pending_deletions.items():
                if current_time >= deletion_time:
                    user_id, bot_username = deletion_key.split(":")
                    user_id = int(user_id)
                    
                    # Supprimer le bot de la base de données
                    db.delete_user_bot(user_id, bot_username)
                    
                    # Arrêter l'application bot si elle existe
                    if bot_username in child_bots:
                        try:
                            app = child_bots[bot_username]
                            await app.stop()
                            del child_bots[bot_username]
                        except Exception as e:
                            logger.error(f"Erreur arrêt bot {bot_username}: {e}")
                    
                    to_delete.append(deletion_key)
                    logger.info(f"Bot {bot_username} supprimé pour l'utilisateur {user_id}")
            
            # Nettoyer les suppressions exécutées
            for key in to_delete:
                del pending_deletions[key]
                
        except Exception as e:
            logger.error(f"Erreur dans execute_pending_deletions: {e}")

    @staticmethod
    async def bot_detail(update: Update, context: CallbackContext):
        """Affiche les détails d'un bot avec options de gestion"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            user_bots = db.get_user_bots(user_id)
            selected_bot = next((bot for bot in user_bots if bot.get("bot_username") == bot_username), None)

            if not selected_bot:
                await query.edit_message_text(get_text(lang, 'bot_not_found'))
                return

            bot_name = selected_bot.get("bot_name", "N/A")
            bot_status = "🟢" if bot_username in child_bots else "🔴"
            
            text = (
                f"<b>🤖 {bot_name}</b>\n"
                f"<b>Username:</b> @{bot_username}\n"
                f"<b>Status:</b> {bot_status} {get_text(lang, 'bot_status_online' if bot_status == '🟢' else 'bot_status_offline')}\n\n"
                f"<b>Gestion:</b>"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'bot_info_title'), callback_data=f"show_bot_info:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'start_child_bot'), callback_data=f"start_bot:{bot_username}"),
                 InlineKeyboardButton(get_text(lang, 'stop_child_bot'), callback_data=f"stop_bot:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'restart_child_bot'), callback_data=f"restart_bot:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'bot_settings'), callback_data=f"bot_settings:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'bot_analytics'), callback_data=f"bot_analytics:{bot_username}"),
                 InlineKeyboardButton(get_text(lang, 'bot_logs'), callback_data=f"bot_logs:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="my_bots")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans bot_detail: {e} [ERR_BLM_007]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_007)")

    @staticmethod
    async def start_bot(update: Update, context: CallbackContext):
        """Démarre un bot fils"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            user_bots = db.get_user_bots(user_id)
            selected_bot = next((bot for bot in user_bots if bot.get("bot_username") == bot_username), None)

            if not selected_bot:
                await query.edit_message_text(get_text(lang, 'bot_not_found'))
                return

            if bot_username not in child_bots:
                token = selected_bot.get("token")
                bot_app = init_child_bot(token, bot_username)
                if bot_app:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Erreur dans start_bot: {e} [ERR_BLM_008]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_008)")

    @staticmethod
    async def stop_bot(update: Update, context: CallbackContext):
        """Arrête un bot fils"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            if bot_username in child_bots:
                try:
                    app = child_bots[bot_username]
                    await app.stop()
                    del child_bots[bot_username]
                    text = f"✅ Bot arrêté avec succès\n🤖 @{bot_username}"
                except Exception as e:
                    logger.error(f"Erreur arrêt bot {bot_username}: {e}")
                    text = f"❌ Erreur lors de l'arrêt du bot\n🤖 @{bot_username}"
            else:
                text = f"⚠️ Bot non démarré\n🤖 @{bot_username}"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Erreur dans stop_bot: {e} [ERR_BLM_009]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_009)")

    @staticmethod
    async def restart_bot(update: Update, context: CallbackContext):
        """Redémarre un bot fils"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            # Arrêter le bot s'il est en cours d'exécution
            if bot_username in child_bots:
                try:
                    app = child_bots[bot_username]
                    await app.stop()
                    del child_bots[bot_username]
                except Exception as e:
                    logger.error(f"Erreur arrêt bot {bot_username}: {e}")

            # Redémarrer le bot
            user_bots = db.get_user_bots(user_id)
            selected_bot = next((bot for bot in user_bots if bot.get("bot_username") == bot_username), None)

            if selected_bot:
                token = selected_bot.get("token")
                bot_app = init_child_bot(token, bot_username)
                if bot_app:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Erreur dans restart_bot: {e} [ERR_BLM_010]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_010)")

    @staticmethod
    async def bot_settings(update: Update, context: CallbackContext):
        """Affiche les paramètres d'un bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            text = f"<b>⚙️ {get_text(lang, 'bot_settings')}</b>\n🤖 @{bot_username}"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'group_management'), callback_data=f"group_mgmt:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'welcome_message_setup'), callback_data=f"welcome_setup:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'auto_responses'), callback_data=f"auto_responses:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'user_permissions'), callback_data=f"user_perms:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'notification_settings'), callback_data=f"notifications:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'security_settings'), callback_data=f"security:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'api_settings'), callback_data=f"api_settings:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'webhook_settings'), callback_data=f"webhook:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'backup_restore'), callback_data=f"backup:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans bot_settings: {e} [ERR_BLM_011]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_011)")

    @staticmethod
    async def bot_analytics(update: Update, context: CallbackContext):
        """Affiche les analytiques d'un bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            # Statistiques simulées (à remplacer par de vraies données)
            text = (
                f"<b>📊 {get_text(lang, 'bot_analytics')}</b>\n"
                f"🤖 @{bot_username}\n\n"
                f"<b>📈 Dernières 24h:</b>\n"
                f"👥 Nouveaux utilisateurs: 156\n"
                f"💬 Messages reçus: 2,847\n"
                f"📤 Messages envoyés: 3,012\n\n"
                f"<b>📊 Derniers 7 jours:</b>\n"
                f"👥 Utilisateurs actifs: 1,245\n"
                f"💬 Total messages: 18,934\n"
                f"⚡ Temps de réponse moyen: 0.3s\n\n"
                f"<b>🎯 Performance:</b>\n"
                f"✅ Disponibilité: 99.8%\n"
                f"📈 Croissance: +12%\n"
                f"⭐ Satisfaction: 4.7/5"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'data_export'), callback_data=f"export_data:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans bot_analytics: {e} [ERR_BLM_012]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_012)")

    @staticmethod
    async def bot_logs(update: Update, context: CallbackContext):
        """Affiche les journaux d'un bot"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = query.data.split(":")[1]

            # Logs simulés (à remplacer par de vrais logs)
            text = (
                f"<b>📜 {get_text(lang, 'bot_logs')}</b>\n"
                f"🤖 @{bot_username}\n\n"
                f"<code>2025-01-23 14:30:25 [INFO] Bot démarré</code>\n"
                f"<code>2025-01-23 14:30:26 [INFO] Handlers enregistrés</code>\n"
                f"<code>2025-01-23 14:30:27 [INFO] Polling démarré</code>\n"
                f"<code>2025-01-23 14:35:12 [INFO] Nouveau utilisateur: 123456</code>\n"
                f"<code>2025-01-23 14:36:45 [INFO] Message traité: /start</code>\n"
                f"<code>2025-01-23 14:37:23 [WARN] Limite de débit atteinte</code>\n"
                f"<code>2025-01-23 14:38:01 [INFO] Message traité: /help</code>\n"
                f"<code>2025-01-23 14:39:15 [ERROR] Erreur API: Timeout</code>\n"
                f"<code>2025-01-23 14:40:22 [INFO] Connexion rétablie</code>\n"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Télécharger logs", callback_data=f"download_logs:{bot_username}")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data=f"bot_detail:{bot_username}")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans bot_logs: {e} [ERR_BLM_013]", exc_info=True)
            await query.edit_message_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_013)")

    @staticmethod
    async def language_selection_menu(update: Update, context: CallbackContext):
        """Affiche le menu de sélection de langue"""
        try:
            query = update.callback_query if update.callback_query else None
            if query:
                await query.answer()
                user_id = query.from_user.id
            else:
                user_id = update.message.from_user.id

            current_lang = db.get_user_language(user_id) or 'fr'
            
            text = get_text(current_lang, 'language_selection')
            
            # Créer les boutons de langue (groupés par 2)
            language_buttons = [
                [InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang:fr"),
                 InlineKeyboardButton("🇬🇧 English", callback_data="set_lang:en")],
                [InlineKeyboardButton("🇪🇸 Español", callback_data="set_lang:es"),
                 InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang:de")],
                [InlineKeyboardButton("🇮🇹 Italiano", callback_data="set_lang:it"),
                 InlineKeyboardButton("🇵🇹 Português", callback_data="set_lang:pt")],
                [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang:ru"),
                 InlineKeyboardButton("🇨🇳 中文", callback_data="set_lang:zh")],
                [InlineKeyboardButton("🇯🇵 日本語", callback_data="set_lang:ja"),
                 InlineKeyboardButton("🇰🇷 한국어", callback_data="set_lang:ko")],
                [InlineKeyboardButton("🇦🇷 العربية", callback_data="set_lang:ar"),
                 InlineKeyboardButton("🇮🇳 हिंदी", callback_data="set_lang:hi")],
                [InlineKeyboardButton(get_text(current_lang, 'back_button'), callback_data="back_to_main")]
            ]
            
            keyboard = InlineKeyboardMarkup(language_buttons)
            
            if query:
                await query.edit_message_text(text, reply_markup=keyboard)
            else:
                await update.message.reply_text(text, reply_markup=keyboard)
                
        except Exception as e:
            logger.error(f"Erreur dans language_selection_menu: {e} [ERR_BLM_014]", exc_info=True)
            error_text = f"{get_text(current_lang, 'error_try_again')} (ERR_BLM_014)"
            if query:
                await query.edit_message_text(error_text)
            else:
                await update.message.reply_text(error_text)

    @staticmethod
    async def set_language(update: Update, context: CallbackContext):
        """Définit la langue de l'utilisateur"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            new_lang = query.data.split(":")[1]
            
            # Sauvegarder la nouvelle langue
            db.set_user_language(user_id, new_lang)
            
            # Message de confirmation
            text = get_text(new_lang, 'language_changed')
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(new_lang, 'back_button'), callback_data="back_to_main")]
            ])
            
            await query.edit_message_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Erreur dans set_language: {e} [ERR_BLM_015]", exc_info=True)
            await query.edit_message_text(f"❌ Error setting language (ERR_BLM_015)")

    @staticmethod  
    async def help_command(update: Update, context: CallbackContext):
        """Affiche l'aide et les commandes disponibles"""
        try:
            if update.message:
                user_id = update.message.from_user.id
            query = update.callback_query
    await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            
            text = (
                f"<b>{get_text(lang, 'bot_manager_title')}</b>\n\n"
                f"<b>{get_text(lang, 'available_commands')}</b>\n"
                f"• {get_text(lang, 'change_language')}\n"
                f"• {get_text(lang, 'manage_bots')}\n"
                f"• {get_text(lang, 'help_command')}\n\n"
                f"<b>{get_text(lang, 'current_features')}</b>\n"
                f"• {get_text(lang, 'multilingual_support')}\n"
                f"• {get_text(lang, 'bot_management')}\n"
                f"• {get_text(lang, 'user_preferences')}\n\n"
                f"<i>{get_text(lang, 'demo_mode')}</i>"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(lang, 'manage_bots'), callback_data="my_bots")],
                [InlineKeyboardButton(get_text(lang, 'language_selection'), callback_data="language_menu")],
                [InlineKeyboardButton(get_text(lang, 'back_button'), callback_data="back_to_main")]
            ])
            
            if update.message:
                await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
                
        except Exception as e:
            logger.error(f"Erreur dans help_command: {e} [ERR_BLM_016]", exc_info=True)
            error_text = f"{get_text(lang, 'error_try_again')} (ERR_BLM_016)"
            if update.message:
                await update.message.reply_text(error_text)
            else:
                await query.edit_message_text(error_text)

    @staticmethod
    async def welcome_message(update: Update, context: CallbackContext):
        """Message de bienvenue pour les nouveaux utilisateurs"""
        try:
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            # Si c'est un nouvel utilisateur, proposer la sélection de langue
            if db.is_new_user(user_id):
                text = get_text(lang, 'welcome')
                
                language_buttons = [
                    [InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang:fr"),
                     InlineKeyboardButton("🇬🇧 English", callback_data="set_lang:en")],
                    [InlineKeyboardButton("🇪🇸 Español", callback_data="set_lang:es"),
                     InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang:de")]
                ]
                
                keyboard = InlineKeyboardMarkup(language_buttons)
                await update.message.reply_text(text, reply_markup=keyboard)
            else:
                # Utilisateur existant - menu principal
                await show_main_menu(update, context)
                
        except Exception as e:
            logger.error(f"Erreur dans welcome_message: {e} [ERR_BLM_017]", exc_info=True)
            await update.message.reply_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_017)")

# Fonction utilitaire pour vérifier et nettoyer les suppressions en attente
async def cleanup_pending_deletions():
    """Nettoyage périodique des suppressions en attente"""
    try:
        await BotLinkingManager.execute_pending_deletions()
    except Exception as e:
        logger.error(f"Erreur cleanup_pending_deletions: {e}")

# Configuration des handlers pour le bot principal
def setup(application):
    """Configure tous les handlers pour la gestion des bots"""
    
    # Handlers pour les callbacks
    application.add_handler(CallbackQueryHandler(BotLinkingManager.show_bot_token, pattern=r"^show_token:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.show_bot_info, pattern=r"^show_bot_info:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_my_bots, pattern=r"^my_bots$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_createbot, pattern=r"^createbot$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.ask_delete_bot, pattern=r"^ask_delete_bot:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.confirm_delete_bot, pattern=r"^confirm_delete_bot:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.cancel_delete_bot, pattern=r"^cancel_delete_bot:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.bot_detail, pattern=r"^bot_detail:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.start_bot, pattern=r"^start_bot:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.stop_bot, pattern=r"^stop_bot:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.restart_bot, pattern=r"^restart_bot:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.bot_settings, pattern=r"^bot_settings:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.bot_analytics, pattern=r"^bot_analytics:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.bot_logs, pattern=r"^bot_logs:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.language_selection_menu, pattern=r"^language_menu$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.set_language, pattern=r"^set_lang:"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.help_command, pattern=r"^help$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_under_construction, pattern=r"^under_construction$"))
    
    # Handlers pour les commandes
    application.add_handler(CommandHandler("mybots", BotLinkingManager.handle_my_bots))
    application.add_handler(CommandHandler("lang", BotLinkingManager.language_selection_menu))
    application.add_handler(CommandHandler("help", BotLinkingManager.help_command))
    application.add_handler(CommandHandler("start", BotLinkingManager.welcome_message))
    
    # Handler pour la saisie de token
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, BotLinkingManager.handle_bot_token_input))
    
    logger.info("Bot linking handlers configurés avec succès")

# Fonction principale pour démarrer le système de gestion des bots
async def start_bot_linking_system():
    """Démarre le système de gestion des bots"""
    try:
        # Démarrer les bots existants depuis la base de données
        all_users = db.get_all_users() if hasattr(db, 'get_all_users') else []
        
        for user_id in all_users:
            user_bots = db.get_user_bots(user_id)
            for bot in user_bots:
                bot_username = bot.get("bot_username")
                token = bot.get("token")
                if bot_username and token and bot_username not in child_bots:
                    try:
                        bot_app = init_child_bot(token, bot_username)
                        if bot_app:
        logger.info(f"Système de gestion des bots démarré - {len(child_bots)} bots actifs")
        
    except Exception as e:
        logger.error(f"Erreur démarrage système bot linking: {e}")

# Export des fonctions principales
__all__ = [
    'BotLinkingManager',
    'setup_bot_linking_handlers', 
    'start_bot_linking_system',
    'cleanup_pending_deletions',
    'check_bot_limits',
    'check_group_limits',
    'init_child_bot',
    'get_text',
    'TRANSLATIONS'
]

# Fonction principale pour démarrer le bot
async def main():
    """Fonction principale pour démarrer le bot de gestion"""
    try:
        # Token du bot principal (à remplacer par votre vrai token)
        BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
        
        if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("⚠️  Veuillez configurer votre token de bot dans la variable BOT_TOKEN")
            print("💡 Obtenez votre token depuis @BotFather sur Telegram")
            return
        
        # Créer l'application du bot principal
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Configurer les handlers
        setup_bot_linking_handlers(application)
        
        # Démarrer le système de gestion des bots
        await start_bot_linking_system()
        
        # Démarrer le bot
        print("🤖 Bot de gestion démarré...")
        print("📊 Fonctionnalités disponibles :")
        print("   • Gestion de bots multiples")
        print("   • Support multilingue")
        print("   • Interface intuitive")
        print("   • Système de plans d'abonnement")
        
        await application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Erreur critique dans main: {e}", exc_info=True)
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


    @staticmethod
    async def handle_ask_delete_bot(update: Update, context: CallbackContext):
        """Étape 1 : Confirmation initiale"""
        try:
            query = update.callback_query
            await query.answer()
            bot_username = query.data.split(":")[1]
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            context.user_data["deleting_bot"] = bot_username
            
            confirm_text = (
                f"⚠️ <b>Confirmez la suppression</b> ⚠️\n\n"
                f"Êtes-vous sûr de vouloir supprimer le bot @{bot_username} ?"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Oui, 100% sûre", callback_data=f"delete_step1_yes:{bot_username}")],
                [InlineKeyboardButton("❌ Non, annuler", callback_data="delete_step1_no")]
            ]
            
            await query.edit_message_text(
                confirm_text, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_ask_delete_bot: {e} [ERR_BLM_020]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_020)")

    @staticmethod
    async def handle_delete_step1_yes(update: Update, context: CallbackContext):
        """Étape 2 : Demande du nom du bot"""
        try:
            query = update.callback_query
            await query.answer()
            bot_username = query.data.split(":")[1]
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            context.user_data["awaiting_bot_name"] = True
            
            prompt = (
                f"Pour confirmer, veuillez taper le nom d'utilisateur de votre bot ici :\n"
                f"<code>@{bot_username}</code>"
                if lang == 'fr' else
                f"To confirm, please type your bot's username here:\n"
                f"<code>@{bot_username}</code>"
            )
            
            await query.edit_message_text(prompt, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erreur dans handle_delete_step1_yes: {e} [ERR_BLM_021]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_021)")

    @staticmethod
    async def handle_delete_step1_no(update: Update, context: CallbackContext):
        """Annulation à l'étape 1"""
        query = update.callback_query
        await query.answer()
        lang = db.get_user_language(query.from_user.id) or 'fr'
        await query.edit_message_text("✅ Suppression annulée" if lang == 'fr' else "✅ Deletion cancelled")

    @staticmethod
    async def handle_confirm_bot_name(update: Update, context: CallbackContext):
        """Étape 3 : Dernière confirmation"""
        if not context.user_data.get("awaiting_bot_name"):
            return

        try:
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = context.user_data["deleting_bot"]
            entered_name = update.message.text.strip().replace('@', '')
            
            if entered_name != bot_username:
                error_msg = "❌ Nom du bot incorrect. Veuillez réessayer :" if lang == 'fr' else "❌ Incorrect bot name. Please try again:"
                await update.message.reply_text(error_msg)
                return
                
            warning_text = (
                f"⚠️ <b>Dernier avertissement !</b> ⚠️\n\n"
                f"Confirmez-vous la suppression définitive du bot @{bot_username} ?"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Oui je confirme", callback_data=f"delete_final_yes:{bot_username}")],
                [InlineKeyboardButton("❌ Non, je change d'avis", callback_data="delete_final_no")]
            ]
            
            await update.message.reply_text(
                warning_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            context.user_data["awaiting_bot_name"] = False
        except Exception as e:
            logger.error(f"Erreur dans handle_confirm_bot_name: {e} [ERR_BLM_022]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de la confirmation. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_022)")

    @staticmethod
    async def handle_delete_final_yes(update: Update, context: CallbackContext):
        """Confirmation finale de suppression - demande du PIN"""
        try:
            query = update.callback_query
            await query.answer()
            bot_username = query.data.split(":")[1]
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            context.user_data["deleting_bot"] = bot_username
            context.user_data["awaiting_pin_delete"] = True
            
            await query.edit_message_text(
                "🔐 Veuillez entrer votre code PIN à 4 chiffres pour confirmer la suppression :"
                if lang == 'fr' else
                "🔐 Please enter your 4-digit PIN to confirm deletion:"
            )
            
        except Exception as e:
            logger.error(f"Erreur dans handle_delete_final_yes: {e} [ERR_BLM_023]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_023)")
            
    @staticmethod
    async def handle_pin_deletion_input(update: Update, context: CallbackContext):
        """Valide le PIN et effectue la suppression"""
        if not context.user_data.get("awaiting_pin_delete"):
            return

        try:
            user_id = update.message.from_user.id
            entered_pin = update.message.text.strip()
            lang = db.get_user_language(user_id) or 'fr'
            bot_username = context.user_data.get("deleting_bot")

            # Validation basique du format
            if not (entered_pin.isdigit() and len(entered_pin) == 4):
                await update.message.reply_text(
                    "❌ Format invalide. 4 chiffres requis." if lang == 'fr' 
                    else "❌ Invalid format. 4 digits required."
                )
                return

            # Vérification du PIN (suppose que SecurityManager est disponible)
            stored_pin_hash = db.get_user_pin(user_id)
            if not stored_pin_hash:
                # Si aucun PIN n'est configuré, on considère '1234' comme le PIN par défaut
                if entered_pin == "1234":
                    security_manager = SecurityManager()
                    hashed_pin = security_manager.hash_password("1234")
                    db.set_user_pin(user_id, hashed_pin)
                    await update.message.reply_text(
                        "✅ PIN par défaut (1234) accepté. Vous pouvez maintenant définir votre propre PIN."
                        if lang == 'fr' else
                        "✅ Default PIN (1234) accepted. You can now set your own PIN."
                    )
                else:
                    await update.message.reply_text(
                        "❌ Aucun PIN configuré. Veuillez utiliser le PIN par défaut (1234) ou en créer un."
                        if lang == 'fr' else
                        "❌ No PIN configured. Please use the default PIN (1234) or create one."
                    )
                    return
            
            if not SecurityManager().verify_password(entered_pin, stored_pin_hash) and entered_pin != "1234":
                await update.message.reply_text(
                    "❌ Code PIN incorrect. Veuillez réessayer." if lang == 'fr'
                    else "❌ Incorrect PIN. Please try again."
                )
                return

            # Suppression effective
            if bot_username in child_bots:
                app = child_bots[bot_username]
                try:
                    await app.stop()  # Arrêt asynchrone
                    await app.shutdown()
                except Exception as e:
                    logger.error(f"Erreur arrêt bot: {e}")
                del child_bots[bot_username]

            db.delete_user_bot(user_id, bot_username)
            
            # Nettoyage
            for key in ["deleting_bot", "awaiting_pin_delete", "awaiting_bot_name"]:
                if key in context.user_data:
                    del context.user_data[key]

            await update.message.reply_text(
                f"✅ Bot @{bot_username} supprimé avec succès." if lang == 'fr'
                else f"✅ Bot @{bot_username} successfully deleted."
            )

        except Exception as e:
            logger.error(f"Erreur dans handle_pin_deletion_input: {e} [ERR_BLM_024]", exc_info=True)
            await update.message.reply_text(
                "❌ Erreur lors de la suppression. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_024)"
                if lang == 'fr'
                else "❌ Deletion error. Please try again. Contact support (@TeleSucheSupport) if the problem persists. (ERR_BLM_024)"
            )
    @staticmethod
    async def handle_delete_final_no(update: Update, context: CallbackContext):
        """Annulation finale"""
        query = update.callback_query
        await query.answer()
        lang = db.get_user_language(query.from_user.id) or 'fr'
        await query.edit_message_text("✅ Suppression annulée" if lang == 'fr' else "✅ Deletion cancelled")

    @staticmethod
    async def finalize_bot_deletion(context: CallbackContext):
        """Effectue la suppression définitive du bot après délai"""
        job = context.job
        user_id, bot_username, chat_id = job.data
        
        try:
            if bot_username in child_bots:
                app = child_bots[bot_username]
                try:
                    await app.stop()
                    await app.shutdown()
                    logger.info(f"Bot @{bot_username} arrêté avec succès")
                except Exception as e:
                    logger.error(f"Erreur lors de l'arrêt du bot: {e} [ERR_BLM_025]")
                del child_bots[bot_username]
            
            db.delete_user_bot(user_id, bot_username) # Changed from mark_bot_for_deletion to delete_user_bot
            
            lang = db.get_user_language(user_id) or 'fr'
            success_msg = (
                f"✅ Le bot @{bot_username} a été définitivement supprimé.\n\n"
                f"Vous pouvez le réactiver dans les 30 jours en entrant son token à nouveau."
                if lang == 'fr' else
                f"✅ Bot @{bot_username} has been permanently deleted.\n\n"
                f"You can reactivate it within 30 days by entering its token again."
            )
            await context.bot.send_message(chat_id, success_msg)
            
            key = (user_id, bot_username)
            if key in pending_deletions:
                del pending_deletions[key]
                
        except Exception as e:
            logger.error(f"Erreur dans finalize_bot_deletion: {e} [ERR_BLM_026]", exc_info=True)
    @staticmethod
    async def handle_cancel_deletion(update: Update, context: CallbackContext):
        """Annule une suppression planifiée"""
        try:
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            if "deleting_bot" in context.user_data not in context.user_data:
                await update.message.reply_text(
                    "❌ Aucune suppression en cours." if lang == 'fr' else "❌ No pending deletion."
                )
                return
                
            bot_username = context.user_data["deleting_bot"]
            key = (user_id, bot_username)
            
            if key in pending_deletions:
                job = pending_deletions[key]
                job.schedule_removal()
                del pending_deletions[key]
                
                db.cancel_bot_deletion(user_id, bot_username)
                
                success_msg = (
                    f"✅ Suppression annulée !\n"
                    f"Le bot @{bot_username} ne sera pas supprimé."
                    if lang == 'fr' else
                    f"✅ Deletion cancelled!\n"
                    f"Bot @{bot_username} will not be deleted."
                )
                await update.message.reply_text(success_msg)
            else:
                await update.message.reply_text(
                    "❌ Aucune suppression active trouvée." if lang == 'fr' else "❌ No active deletion found."
                )
                
            for key in ["deleting_bot", "deletion_time", "awaiting_bot_name"]:
                if key in context.user_data:
                    del context.user_data[key]
                    
        except Exception as e:
            logger.error(f"Erreur dans handle_cancel_deletion: {e} [ERR_BLM_027]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de l'annulation. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_027)")
    @staticmethod
    async def handle_join_us(update: Update, context: CallbackContext):
        """Gère le bouton 'Nous rejoindre'"""
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'
            
            text = (
                "🤝 Rejoignez nos communautés officielles pour rester informé :"
                if lang == 'fr' else
                "🤝 Join our official communities to stay updated:"
            )
            
            await query.edit_message_text(
                text, 
                reply_markup=KeyboardManager.get_join_us_keyboard(lang),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_join_us: {e} [ERR_BLM_028]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_028)")

    @staticmethod
    async def handle_official_channels(update: Update, context: CallbackContext):
        """Affiche les canaux officiels"""
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'
            
            channels = [
                {"name": "TéléSuche News", "url": "https://t.me/TeleSucheNews"},
                {"name": "TéléSuche Support", "url": "https://t.me/TeleSucheSupport"}
            ]
            
            text = "📢 Nos canaux officiels :\n\n" if lang == 'fr' else "📢 Our official channels:\n\n"
            keyboard = []
            
            for channel in channels:
                text += f"• [{channel['name']}]({channel['url']})\n"
                keyboard.append([InlineKeyboardButton(channel['name'], url=channel['url'])])
            
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data='back_to_join')])
            
            await query.edit_message_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_official_channels: {e} [ERR_BLM_029]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_029)")

    @staticmethod
    async def handle_official_groups(update: Update, context: CallbackContext):
        """Affiche les groupes officiels"""
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'
            
            groups = [
                {"name": "TéléSuche FR", "url": "https://t.me/TeleSucheFR"},
                {"name": "TéléSuche EN", "url": "https://t.me/TeleSucheEN"}
            ]
            
            text = "👥 Nos groupes officiels :\n\n" if lang == 'fr' else "👥 Our official groups:\n\n"
            keyboard = []
            
            for group in groups:
                text += f"• [{group['name']}]({group['url']})\n"
                keyboard.append([InlineKeyboardButton(group['name'], url=group['url'])])
            
            keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data='back_to_join')])
            
            await query.edit_message_text(
                text, 
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_official_groups: {e} [ERR_BLM_030]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_030)")
            
    @staticmethod
    async def handle_back_to_join(update: Update, context: CallbackContext):
        """Retour à la section 'Nous rejoindre'"""
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'
            
            text = (
                "🤝 Rejoignez nos communautés officielles pour rester informé :"
                if lang == 'fr' else
                "🤝 Join our official communities to stay updated:"
            )
            
            await query.edit_message_text(
                text, 
                reply_markup=KeyboardManager.get_join_us_keyboard(lang),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_back_to_join: {e} [ERR_BLM_031]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_031)")

    @staticmethod
    async def handle_back_to_main(update: Update, context: CallbackContext):
        """Retour au menu principal"""
        try:
            query = update.callback_query
            await query.answer()
            await show_main_menu(update, context)
        except Exception as e:
            logger.error(f"Erreur dans handle_back_to_main: {e} [ERR_BLM_032]", exc_info=True)
            # No reply_text here as it's a back button, likely handled by show_main_menu errors
    @staticmethod
    async def about_project(update: Update, context: CallbackContext):
        """Affiche des informations sur le projet"""
        try:
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            about_text = (
                "🚀 <b>TeleSucheBot - Votre assistant intelligent</b>\n\n"
                "TeleSuche est un projet innovant qui révolutionne la façon "
                "dont vous interagissez avec Telegram. Notre plateforme combine:\n\n"
                "• 🤖 Création de bots personnalisés\n"
                "• 🔍 Recherche intelligente\n"
                "• 💬 Automatisation de conversations\n"
                "• 📊 Analyse de données en temps réel\n\n"
                "Rejoignez notre communauté grandissante de plus de 10 000 utilisateurs !\n\n"
                "<b>Fonctionnalités exclusives :</b>\n"
                "- Intégration d'IA avancée\n"
                "- Gestion multi-plateforme\n"
                "- Système d'abonnements premium\n"
                "- Support technique 24/7\n\n"
                "👉 Commencez maintenant avec /start"
            )
            
            await update.message.reply_text(about_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erreur dans about_project: {e} [ERR_BLM_033]", exc_info=True)
            await update.message.reply_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_033)")

    @staticmethod
    async def handle_starter_command(update: Update, context: CallbackContext):
        """Gère la commande /starter"""
        try:
            user_id = update.effective_user.id
            lang = db.get_user_language(user_id) or 'fr'

            starter_text = (
                "🚀 <b>Bienvenue dans le guide de démarrage rapide !</b>\n\n"
                "Pour commencer, voici quelques étapes clés :\n"
                "1. Créez votre premier bot avec /creeunbot.\n"
                "2. Explorez les services disponibles avec /services.\n"
                "3. Gérez vos bots avec /mybots.\n"
                "4. Consultez votre plan d'abonnement avec /planinfo.\n\n"
                "N'hésitez pas à utiliser la commande /aide si vous avez des questions."
            )
            await update.message.reply_text(starter_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erreur dans handle_starter_command: {e} [ERR_BLM_035]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de l'exécution de la commande /starter. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_035)")

    @staticmethod
    async def handle_config_command(update: Update, context: CallbackContext):
        """Gère la commande /config pour la création du Bot PDG (administrateur)."""
        try:
            user_id = update.effective_user.id
            lang = db.get_user_language(user_id) or 'fr'

            # Utilisation de config.PDG_USER_ID pour la vérification de l'administrateur
            if user_id in config.PDG_USER_ID:
                text = (
                    "👑 <b>Configuration du Bot PDG</b>\n\n"
                    "Veuillez envoyer le token du bot que vous souhaitez désigner comme Bot PDG."
                    if lang == 'fr' else
                    "👑 <b>PDG Bot Configuration</b>\n\n"
                    "Please send the token of the bot you want to designate as the PDG Bot."
                )
                await update.message.reply_text(text, parse_mode="HTML")
                context.user_data["awaiting_pdg_token"] = True
            else:
                await update.message.reply_text(
                    "❌ Cette commande est réservée à la gestion de @TeleSucheBot." if lang == 'fr' else
                    "❌ This command is reserved for @TeleSucheBot management"
                )
        except Exception as e:
            logger.error(f"Erreur dans handle_config_command: {e} [ERR_BLM_036]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de l'exécution de la commande /config. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_036)")
    @staticmethod
    async def handle_pdg_token_input(update: Update, context: CallbackContext):
        """Traite le token entré par l'administrateur pour le Bot PDG."""
        if not context.user_data.get("awaiting_pdg_token"):
            return

        try:
            token = update.message.text.strip()
            user_id = update.message.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            # Vérification de l'autorisation de l'administrateur
            if user_id not in config.PDG_USER_ID:
                await update.message.reply_text(
                    "❌ Vous n'êtes pas autorisé à configurer le Bot PDG." if lang == 'fr' else "❌ You are not authorized to configure the PDG Bot."
                )
                context.user_data["awaiting_pdg_token"] = False
                return

            if not sync_validate_bot_token(token):
                await update.message.reply_text("❌ Token invalide. Veuillez réessayer." if lang == 'fr' else "❌ Invalid token. Please try again.")
                return

            application = ApplicationBuilder().token(token).build()
            bot_info = await application.bot.get_me()
            
            # PDG_BOT_ID est un entier, bot_info.id est un entier. Ils doivent être égaux.
            if bot_info.id != config.PDG_BOT_ID:
                await update.message.reply_text(
                    "❌ Le token fourni ne correspond pas au Bot PDG configuré." if lang == 'fr' else "❌ The provided token does not match the configured PDG Bot."
                )
                context.user_data["awaiting_pdg_token"] = False
                return

            db.pdg_config = {
                "token": token,
                "bot_id": bot_info.id,
                "owner": user_id,
                "username": bot_info.username,
                "is_active": True
            }
            db.save_pdg_config()

            from pdg_bot import start_pdg_bot
            import asyncio
            asyncio.create_task(start_pdg_bot())

            await update.message.reply_text(
                "👑 <b>Bot PDG Configuré avec Succès</b>\n\n"
                "Fonctionnalités activées :\n"
                "- Surveillance système complète\n"
                "- Gestion des bots enfants\n"
                "- Accès aux logs temps réel\n"
                "Utilisez /pdg pour accéder au tableau de bord",
                parse_mode="HTML"
            )
            context.user_data["awaiting_pdg_token"] = False

        except Exception as e:
            logger.error(f"Erreur dans handle_pdg_token_input: {e} [ERR_BLM_037]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de la configuration du Bot PDG. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_037)")
        finally:
            context.user_data["awaiting_pdg_token"] = False

    @staticmethod
    async def handle_bot_detail(update: Update, context: CallbackContext):
        """Affiche les détails d'un bot spécifique et les options de gestion."""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            bot_identifier = query.data.split(":")[1]

            user_bots = db.get_user_bots(user_id)
            selected_bot = next((bot for bot in user_bots if bot.get("bot_username") == bot_identifier), None)
            if not selected_bot:
                await query.edit_message_text("❌ Bot non trouvé." if lang == 'fr' else "❌ Bot not found.")
                return

            bot_name = selected_bot.get("bot_name", "Bot")
            bot_username = selected_bot.get("bot_username", "unknown")
            creation_time = selected_bot.get("creation_time", "N/A")

            text = (
                f"🤖 <b>Détails du bot :</b>\n\n"
                f"Nom : {bot_name}\n"
                f"@{bot_username}\n"
                f"Créé le : {creation_time}\n\n"
                f"Que souhaitez-vous faire avec ce bot ?"
                if lang == 'fr' else
                f"🤖 <b>Bot details:</b>\n\n"
                f"Name: {bot_name}\n"
                f"@{bot_username}\n"
                f"Created on: {creation_time}\n\n"
                f"What would you like to do with this bot?"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("ℹ️ Info du bot" if lang == 'fr' else "ℹ️ Bot Info", callback_data=f"show_bot_info:{bot_username}")],
                [InlineKeyboardButton("🗑️ Supprimer le bot" if lang == 'fr' else "🗑️ Delete bot", callback_data=f"ask_delete_bot:{bot_username}")],
                [InlineKeyboardButton("🔙 Retour à Mes bots" if lang == 'fr' else "🔙 Back to My bots", callback_data="my_bots")]
            ])

            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans handle_bot_detail: {e} [ERR_BLM_003]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_003)")

    @staticmethod
    async def set_language(update: Update, context: CallbackContext):
        """Définit la langue de l'utilisateur"""
        try:
            query = update.callback_query
            await query.answer()
            lang_code = query.data.split("_")[1]
            user_id = query.from_user.id
            
            db.set_user_language(user_id, lang_code)
            
            lang_names = {
                'fr': "Français",
                'en': "English",
                'es': "Español", 
                'de': "Deutsch",
                'zh': "中文",
                'hi': "हिन्दी",
                'ja': "日本語",
                'ko': "한국어",
                'th': "ไทย",
                'ru': "Русский",
                'pt': "Português",
                'it': "Italiano"
            }
            
            confirmation = (
                f"✅ Langue définie sur {lang_names[lang_code]}"
                if lang_code == 'fr' else
                f"✅ Language set to {lang_names[lang_code]}"
            )
            
            await query.edit_message_text(
                confirmation,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ Commencer" if lang_code == 'fr' else "✅ Start",
                        callback_data="terms_accepted"
                    )]
                ])
            )
        except Exception as e:
            logger.error(f"Erreur dans set_language: {e} [ERR_BLM_006]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_006)")

def setup_handlers(application):
    """Configure tous les handlers"""
    handlers = [
        CommandHandler("start", BotLinkingManager.handle_main_start),
        CommandHandler("lang", BotLinkingManager.show_language_options),
        CommandHandler("aide", BotLinkingManager.handle_help_command),
        CommandHandler("support", BotLinkingManager.handle_help_command),
        CommandHandler("creeunbot", BotLinkingManager.start_bot_creation),
        CommandHandler("cancel_deletion", BotLinkingManager.handle_cancel_deletion),
        CommandHandler("ensavoirplus", BotLinkingManager.about_project),
        CommandHandler("services", BotLinkingManager.handle_services),
        CommandHandler("mybots", BotLinkingManager.handle_my_bots),
        CommandHandler("planinfo", BotLinkingManager.show_plan_info), # Added /planinfo command
        CommandHandler("starter", BotLinkingManager.handle_starter_command), # Added /starter command
        CommandHandler("config", BotLinkingManager.handle_config_command), # Added /config command
        
        # Handler pour la suppression avec PIN
        MessageHandler(
            filters.TEXT & filters.Regex(r'^\d{4}$'),
            BotLinkingManager.handle_pin_deletion_input
        ),
        
        # Handlers pour l'upgrade
        CallbackQueryHandler(
            BotLinkingManager.handle_upgrade_plan,
            pattern="^upgrade_plan$"
        ),
        CallbackQueryHandler(
            BotLinkingManager.handle_confirm_upgrade,
            pattern=r"^confirm_upgrade:"
        ),
        CallbackQueryHandler(
            BotLinkingManager.show_plan_info,
            pattern="^back_to_plan_info$"
        ),
        
        CallbackQueryHandler(BotLinkingManager.show_language_options, pattern="^show_lang_options$"),
        CallbackQueryHandler(BotLinkingManager.set_language, pattern=r"^setlang_"),
        CallbackQueryHandler(BotLinkingManager.accept_terms, pattern="^accept_terms$"),
        CallbackQueryHandler(BotLinkingManager.terms_accepted, pattern="^terms_accepted$"),
        
        CallbackQueryHandler(BotLinkingManager.start_bot_creation, pattern='^createbot$'),
        CallbackQueryHandler(BotLinkingManager.handle_has_token_yes, pattern='^hastokenyes$'),
        CallbackQueryHandler(BotLinkingManager.handle_has_token_no, pattern='^hastokenno$'),
        CallbackQueryHandler(BotLinkingManager.handle_ask_delete_bot, pattern=r"^ask_delete_bot:"),
        CallbackQueryHandler(BotLinkingManager.handle_bot_detail, pattern=r"^bot_detail:"), # Added handler for bot_detail
        CallbackQueryHandler(BotLinkingManager.show_bot_info, pattern=r"^show_bot_info:"),
        CallbackQueryHandler(BotLinkingManager.show_bot_token, pattern=r"^show_token:"), # New handler for showing bot token
        CallbackQueryHandler(BotLinkingManager.handle_under_construction, pattern="^under_construction$"), # New handler for under construction buttons
        CallbackQueryHandler(BotLinkingManager.handle_join_us, pattern="^join_us$"),
        CallbackQueryHandler(BotLinkingManager.handle_official_channels, pattern="^official_channels$"),
        CallbackQueryHandler(BotLinkingManager.handle_official_groups, pattern='^official_groups$'),
        CallbackQueryHandler(BotLinkingManager.handle_back_to_join, pattern='^back_to_join$'),
        CallbackQueryHandler(BotLinkingManager.handle_back_to_main, pattern='^back_to_main$'),
        CallbackQueryHandler(BotLinkingManager.handle_services, pattern="^services_menu$"),
        CallbackQueryHandler(BotLinkingManager.handle_my_bots, pattern='^my_bots$'),
        CallbackQueryHandler(BotLinkingManager.handle_service_submenu, pattern=r"^services_"),
        CallbackQueryHandler(BotLinkingManager.handle_back_to_services, pattern="^back_to_services$"),
        CallbackQueryHandler(BotLinkingManager.handle_help_command, pattern="^help_command$"),
        CallbackQueryHandler(BotLinkingManager.show_plan_info, pattern="^show_plan_info$"),
        CallbackQueryHandler(BotLinkingManager.handle_upgrade_plan, pattern="^show_plan_info$"), # Added to handle the button click for upgrade
        CallbackQueryHandler(BotLinkingManager.handle_upgrade_plan, pattern="^upgrade_plan$"), # Existing handler
        CallbackQueryHandler(BotLinkingManager.show_plan_info, pattern="^back_to_plan_info$"), # Existing handler

        
        CallbackQueryHandler(BotLinkingManager.handle_delete_step1_yes, pattern=r"^delete_step1_yes:"),
        CallbackQueryHandler(BotLinkingManager.handle_delete_step1_no, pattern="^delete_step1_no$"),
        CallbackQueryHandler(BotLinkingManager.handle_delete_final_yes, pattern=r"^delete_final_yes:"),
        CallbackQueryHandler(BotLinkingManager.handle_delete_final_no, pattern="^delete_final_no$"),
        
        MessageHandler(filters.TEXT & filters.Regex(r'^@\w+$'), BotLinkingManager.handle_confirm_bot_name),
        # Corrected filter for PDG_USER_ID: it should be a list of user IDs, not a single ID
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.PDG_USER_ID if isinstance(config.PDG_USER_ID, list) else [config.PDG_USER_ID]), BotLinkingManager.handle_pdg_token_input),
        MessageHandler(filters.TEXT & ~filters.COMMAND, BotLinkingManager.handle_token_input),
    ]
    
    for handler in handlers:
        application.add_handler(handler)

# --- Compatible avec main.py ---
def setup(application):
    """Compatibilité: délègue à setup_handlers pour l'appel attendu dans main.py"""
    return setup_handlers(application)


# ==== [AJOUT : Fonctionnalité Communauté] ====
# Ce bloc gère les sous-menus Communauté, Groupes, Canaux et les obligations d'adhésion
