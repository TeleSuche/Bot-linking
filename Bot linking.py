import logging
logger = logging.getLogger(__name__)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackContext, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ApplicationBuilder

from typing import Dict, Optional
from datetime import datetime, timedelta

from utils.memory_full import db
from utils.api_client import sync_validate_bot_token
from utils.menu_utils import show_main_menu
from utils.user_features import get_welcome_message
from config import config
from utils.security import SecurityManager
from handlers.subscriptions import PLANS, get_user_plan, get_plan_limits
from modepay import PaymentProcessor

# États utilisateur
from enum import Enum

class UserStates(Enum):
    INITIAL = "initial"
    AWAITING_TOKEN = "awaiting_token"
    SELECTING_LANGUAGE = "selecting_language"

PDG_USER_ID = config.PDG_USER_ID

pending_deletions = {}

# Déclaration de child_bots
child_bots: Dict[str, Application] = {}

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
        "health": "🟢",
        "monetization": "Active"
    }
}

def init_child_bot(token: str, bot_username: str) -> Optional[Application]:
    """Initialise un bot enfant de manière sécurisée"""
    try:
        application = (
            ApplicationBuilder()
            .token(token)
            .connect_timeout(30)
            .read_timeout(30)
            .pool_timeout(30)
            .build()
        )
        
        if "child_bots" not in application.shared_data:
            application.shared_data["child_bots"] = {}
            
        application.shared_data["child_bots"][bot_username] = application
        return application
        
    except Exception as e:
        logger.error(f"Erreur initialisation bot fils: {e}")
        return None

async def check_bot_limits(user_id: int) -> bool:
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    if plan == "free":
        trial_end_date = db.get_user_trial_end_date(user_id)
        if trial_end_date and datetime.now() < datetime.fromisoformat(trial_end_date):
            if len(user_bots) >= 10:
                return False
        else:
            if len(user_bots) >= plan_limits["bots"]:
                return False
    else:
        if len(user_bots) >= plan_limits["bots"]:
            return False
    return True

async def check_group_limits(user_id: int, new_group_id: int = 0) -> bool:
    plan = get_user_plan(user_id)
    user_bots = db.get_user_bots(user_id)
    plan_limits = get_plan_limits(plan)
    
    total_groups = sum(len(bot.get("groups", [])) for bot in user_bots)
    if new_group_id > 0:
        total_groups += 1
    
    if total_groups >= plan_limits["groups"]:
        return False
    return True

def delete_user_bot(user_id: int, bot_username: str) -> bool:
    if user_id in db.bots:
        db.bots[user_id] = [bot for bot in db.bots[user_id] 
                          if bot.get('bot_username') != bot_username]
        return True
    return False
        
def cancel_bot_deletion(user_id: int, bot_username: str):
    key = f"{user_id}:{bot_username}"
    if key in pending_deletions:
        del pending_deletions[key]
    db.cancel_bot_deletion(user_id, bot_username)
        
def save_terms_acceptance(user_id: int):
    if user_id not in db.users:
        db.users[user_id] = {}
    db.users[user_id]['terms_accepted'] = True
        
def get_user_trial_end_date(user_id: int):
    return db.users.get(user_id, {}).get('trial_end_date')

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
        'data_export': "Exporter les données",
        'terms_declined': "Vous devez accepter les CGU pour utiliser le service",
        'begin_button': "Commencer",
        'start_button': "Démarrer",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
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
        'data_export': "Export data",
        'terms_declined': "You must accept TOS to use the service",
        'begin_button': "Begin",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'es': {
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
        "data_export": "Exportar datos",
        "terms_declined": "Debes aceptar los términos de servicio para usar el servicio",
        "begin_button": "Comenzar",
        "start_button": "Iniciar",
        "token_format": "Formato: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'de': {
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
        "data_export": "Daten exportieren",
        "terms_declined": "Sie müssen die Nutzungsbedingungen akzeptieren, um den Service zu nutzen",
        "begin_button": "Beginnen",
        "start_button": "Starten",
        "token_format": "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'zh': {
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
        "data_export": "导出数据",
        "terms_declined": "您必须接受服务条款才能使用该服务",
        "begin_button": "开始",
        "start_button": "启动",
        "token_format": "格式: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'hi': {
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
    },
    'ja': {
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
    },
    'ko': {
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
    },
    'th': {
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
    },
    'ru': {
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
    },
    'pt': {
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
    },
    'it': {
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
    },
    'ar': {
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
    },
    'tr': {
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
        "data_export": "Verileri dışa aktar",
        "terms_declined": "Hizmeti kullanmak için Hizmet Şartlarını kabul etmelisiniz",
        "begin_button": "Başla",
        "start_button": "Başlat",
        "token_format": "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'pl': {
        'bot_token': "Token bota",
        'token_not_found': "Token nie znaleziony",
        'bot_not_found': "Bot nie znaleziony",
        'error_try_again': "Błąd, spróbuj ponownie",
        'back_button': "Wstecz",
        'cancel': "Anuluj",
        'token_invalid': "Nieprawidłowy token",
        'welcome': "Witamy! Wybierz swój język:",
        'terms_declined': "Musisz zaakceptować Regulamin, aby korzystać z usługi",
        'begin_button': "Rozpocznij",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'nl': {
        'bot_token': "Bot token",
        'token_not_found': "Token niet gevonden",
        'bot_not_found': "Bot niet gevonden",
        'error_try_again': "Fout, probeer opnieuw",
        'back_button': "Terug",
        'cancel': "Annuleren",
        'token_invalid': "Ongeldig token",
        'welcome': "Welkom! Kies je taal:",
        'terms_declined': "Je moet de Servicevoorwaarden accepteren om de service te gebruiken",
        'begin_button': "Begin",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'sv': {
        'bot_token': "Bot token",
        'token_not_found': "Token hittades inte",
        'bot_not_found': "Bot hittades inte",
        'error_try_again': "Fel, försök igen",
        'back_button': "Tillbaka",
        'cancel': "Avbryt",
        'token_invalid': "Ogiltigt token",
        'welcome': "Välkommen! Välj ditt språk:",
        'terms_declined': "Du måste acceptera Användarvillkoren för att använda tjänsten",
        'begin_button': "Börja",
        'start_button': "Starta",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'no': {
        'bot_token': "Bot token",
        'token_not_found': "Token ikke funnet",
        'bot_not_found': "Bot ikke funnet",
        'error_try_again': "Feil, vennligst prøv igjen",
        'back_button': "Tilbake",
        'cancel': "Avbryt",
        'token_invalid': "Ugyldig token",
        'welcome': "Velkommen! Velg ditt språk:",
        'terms_declined': "Du må akseptere Tjenestevilkårene for å bruke tjenesten",
        'begin_button': "Begynn",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'da': {
        'bot_token': "Bot token",
        'token_not_found': "Token ikke fundet",
        'bot_not_found': "Bot ikke fundet",
        'error_try_again': "Fejl, prøv venligst igen",
        'back_button': "Tilbage",
        'cancel': "Annuller",
        'token_invalid': "Ugyldigt token",
        'welcome': "Velkommen! Vælg dit sprog:",
        'terms_declined': "Du skal acceptere Servicevilkårene for at bruge tjenesten",
        'begin_button': "Begynd",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'fi': {
        'bot_token': "Bot token",
        'token_not_found': "Tokenia ei löytynyt",
        'bot_not_found': "Bottia ei löytynyt",
        'error_try_again': "Virhe, yritä uudelleen",
        'back_button': "Takaisin",
        'cancel': "Peruuta",
        'token_invalid': "Virheellinen token",
        'welcome': "Tervetuloa! Valitse kielesi:",
        'terms_declined': "Sinun täytyy hyväksyä Käyttöehdot käyttääksesi palvelua",
        'begin_button': "Aloita",
        'start_button': "Käynnistä",
        'token_format': "Muoto: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'he': {
        'bot_token': "טוקן בוט",
        'token_not_found': "טוקן לא נמצא",
        'bot_not_found': "בוט לא נמצא",
        'error_try_again': "שגיאה, נסה שוב",
        'back_button': "חזור",
        'cancel': "ביטול",
        'token_invalid': "טוקן לא תקין",
        'welcome': "ברוכים הבאים! בחר את השפה שלך:",
        'terms_declined': "עליך לקבל את תנאי השירות כדי להשתמש בשירות",
        'begin_button': "התחל",
        'start_button': "הפעל",
        'token_format': "פורמט: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'cs': {
        'bot_token': "Bot token",
        'token_not_found': "Token nebyl nalezen",
        'bot_not_found': "Bot nebyl nalezen",
        'error_try_again': "Chyba, zkuste to znovu",
        'back_button': "Zpět",
        'cancel': "Zrušit",
        'token_invalid': "Neplatný token",
        'welcome': "Vítejte! Vyberte svůj jazyk:",
        'terms_declined': "Musíte přijmout Podmínky služby, abyste mohli službu používat",
        'begin_button': "Začít",
        'start_button': "Start",
        'token_format': "Formát: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'sk': {
        'bot_token': "Bot token",
        'token_not_found': "Token sa nenašiel",
        'bot_not_found': "Bot sa nenašiel",
        'error_try_again': "Chyba, skúste znova",
        'back_button': "Späť",
        'cancel': "Zrušiť",
        'token_invalid': "Neplatný token",
        'welcome': "Vitajte! Vyberte si svoj jazyk:",
        'terms_declined': "Musíte prijať Podmienky služby, aby ste mohli službu používať",
        'begin_button': "Začať",
        'start_button': "Štart",
        'token_format': "Formát: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'hu': {
        'bot_token': "Bot token",
        'token_not_found': "A token nem található",
        'bot_not_found': "A bot nem található",
        'error_try_again': "Hiba, kérlek próbáld újra",
        'back_button': "Vissza",
        'cancel': "Mégse",
        'token_invalid': "Érvénytelen token",
        'welcome': "Üdvözöljük! Válaszd ki a nyelved:",
        'terms_declined': "El kell fogadnod a Szolgáltatási Feltételeket a szolgáltatás használatához",
        'begin_button': "Kezdés",
        'start_button': "Indítás",
        'token_format': "Formátum: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'ro': {
        'bot_token': "Token bot",
        'token_not_found': "Token-ul nu a fost găsit",
        'bot_not_found': "Bot-ul nu a fost găsit",
        'error_try_again': "Eroare, încearcă din nou",
        'back_button': "Înapoi",
        'cancel': "Anulează",
        'token_invalid': "Token invalid",
        'welcome': "Bun venit! Alege limba ta:",
        'terms_declined': "Trebuie să accepți Termenii de Serviciu pentru a folosi serviciul",
        'begin_button': "Începe",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'bg': {
        'bot_token': "Токен на бота",
        'token_not_found': "Токенът не е намерен",
        'bot_not_found': "Ботът не е намерен",
        'error_try_again': "Грешка, моля опитайте отново",
        'back_button': "Назад",
        'cancel': "Отказ",
        'token_invalid': "Невалиден токен",
        'welcome': "Добре дошли! Изберете вашия език:",
        'terms_declined': "Трябва да приемете Условията за обслужване, за да използвате услугата",
        'begin_button': "Започни",
        'start_button': "Старт",
        'token_format': "Формат: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'hr': {
        'bot_token': "Bot token",
        'token_not_found': "Token nije pronađen",
        'bot_not_found': "Bot nije pronađen",
        'error_try_again': "Greška, molimo pokušajte ponovo",
        'back_button': "Nazad",
        'cancel': "Otkaži",
        'token_invalid': "Nevažeći token",
        'welcome': "Dobrodošli! Odaberite vaš jezik:",
        'terms_declined': "Morate prihvatiti Uslove korišćenja da biste koristili uslugu",
        'begin_button': "Počni",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'sl': {
        'bot_token': "Bot žeton",
        'token_not_found': "Žeton ni najden",
        'bot_not_found': "Bot ni najden",
        'error_try_again': "Napaka, poskusite znova",
        'back_button': "Nazaj",
        'cancel': "Prekliči",
        'token_invalid': "Neveljaven žeton",
        'welcome': "Dobrodošli! Izberite svoj jezik:",
        'terms_declined': "Sprejeti morate Pogoje storitve, da lahko uporabljate storitev",
        'begin_button': "Začni",
        'start_button': "Začetek",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'uk': {
        'bot_token': "Токен бота",
        'token_not_found': "Токен не знайдено",
        'bot_not_found': "Бот не знайдено",
        'error_try_again': "Помилка, спробуйте ще раз",
        'back_button': "Назад",
        'cancel': "Скасувати",
        'token_invalid': "Недійсний токен",
        'welcome': "Ласкаво просимо! Оберіть вашу мову:",
        'terms_declined': "Ви повинні прийняти Умови обслуговування, щоб використовувати сервіс",
        'begin_button': "Почати",
        'start_button': "Старт",
        'token_format': "Формат: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'vi': {
        'bot_token': "Token bot",
        'token_not_found': "Không tìm thấy token",
        'bot_not_found': "Không tìm thấy bot",
        'error_try_again': "Lỗi, vui lòng thử lại",
        'back_button': "Quay lại",
        'cancel': "Hủy",
        'token_invalid': "Token không hợp lệ",
        'welcome': "Chào mừng! Chọn ngôn ngữ của bạn:",
        'terms_declined': "Bạn phải chấp nhận Điều khoản Dịch vụ để sử dụng dịch vụ",
        'begin_button': "Bắt đầu",
        'start_button': "Khởi động",
        'token_format': "Định dạng: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'id': {
        'bot_token': "Token bot",
        'token_not_found': "Token tidak ditemukan",
        'bot_not_found': "Bot tidak ditemukan",
        'error_try_again': "Error, silakan coba lagi",
        'back_button': "Kembali",
        'cancel': "Batal",
        'token_invalid': "Token tidak valid",
        'welcome': "Selamat datang! Pilih bahasa Anda:",
        'terms_declined': "Anda harus menerima Syarat Layanan untuk menggunakan layanan",
        'begin_button': "Mulai",
        'start_button': "Start",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    },
    'ms': {
        'bot_token': "Token bot",
        'token_not_found': "Token tidak dijumpai",
        'bot_not_found': "Bot tidak dijumpai",
        'error_try_again': "Ralat, sila cuba lagi",
        'back_button': "Kembali",
        'cancel': "Batal",
        'token_invalid': "Token tidak sah",
        'welcome': "Selamat datang! Pilih bahasa anda:",
        'terms_declined': "Anda mesti menerima Syarat Perkhidmatan untuk menggunakan perkhidmatan",
        'begin_button': "Mula",
        'start_button': "Mula",
        'token_format': "Format: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    }
}

# Liste des 28 langues supportées dans l'ordre de la grille 7x4
SUPPORTED_LANGUAGES = [
    ('🇫🇷', 'fr', 'Français'),
    ('🇬🇧', 'en', 'English'),
    ('🇪🇸', 'es', 'Español'),
    ('🇩🇪', 'de', 'Deutsch'),
    ('🇨🇳', 'zh', '简体中文'),
    ('🇷🇺', 'ru', 'Русский'),
    ('🇵🇹', 'pt', 'Português'),
    ('🇮🇹', 'it', 'Italiano'),
    ('🇦🇷', 'ar', 'العربية'),
    ('🇹🇷', 'tr', 'Türkçe'),
    ('🇯🇵', 'ja', '日本語'),
    ('🇰🇷', 'ko', '한국어'),
    ('🇹🇭', 'th', 'ไทย'),
    ('🇮🇳', 'hi', 'हिन्दी'),
    ('🇻🇳', 'vi', 'Tiếng Việt'),
    ('🇵🇱', 'pl', 'Polski'),
    ('🇳🇱', 'nl', 'Nederlands'),
    ('🇸🇪', 'sv', 'Svenska'),
    ('🇳🇴', 'no', 'Norsk'),
    ('🇩🇰', 'da', 'Dansk'),
    ('🇫🇮', 'fi', 'Suomi'),
    ('🇮🇱', 'he', 'עברית'),
    ('🇨🇿', 'cs', 'Čeština'),
    ('🇸🇰', 'sk', 'Slovenčina'),
    ('🇭🇺', 'hu', 'Magyar'),
    ('🇷🇴', 'ro', 'Română'),
    ('🇧🇬', 'bg', 'Български'),
    ('🇭🇷', 'hr', 'Hrvatski')
]

def create_language_selection_keyboard():
    """Crée la grille 7x4 boutons pour la sélection des 28 langues"""
    keyboard = []
    languages = SUPPORTED_LANGUAGES
    
    # Créer la grille 7 rangées x 4 colonnes = 28 boutons
    for row in range(7):
        row_buttons = []
        for col in range(4):
            index = row * 4 + col
            if index < len(languages):
                flag, code, name = languages[index]
                button_text = f"{flag} {name}"
                callback_data = f"set_language:{code}"
                row_buttons.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        if row_buttons:
            keyboard.append(row_buttons)
    
    return InlineKeyboardMarkup(keyboard)

async def show_language_selection(update: Update):
    """Affiche la sélection de langue avec grille 7x4 boutons pour 28 langues"""
    try:
        keyboard = create_language_selection_keyboard()
        
        welcome_text = ("🌍 Bienvenue ! Choisissez votre langue\n"
                       "🌍 Welcome! Choose your language\n"
                       "🌍 ¡Bienvenido! Elige tu idioma\n"
                       "🌍 Willkommen! Wählen Sie Ihre Sprache")
        
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=keyboard)
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Erreur dans show_language_selection: {e}")
        return None

# Classe principale pour la gestion des bots
class BotLinkingManager:
    @staticmethod
    async def set_language_callback(update: Update, context: CallbackContext):
        """Gestionnaire pour la sélection de langue depuis la grille 7x4"""
        query = update.callback_query
        await query.answer()
        lang_code = query.data.split(":")[1]
        user_id = query.from_user.id
        
        try:
            # Sauvegarder la langue sélectionnée
            db.set_user_language(user_id, lang_code)
            
            # Mapping des noms de langues pour les 28 langues
            lang_names = {
                'fr': "Français", 'en': "English", 'es': "Español", 'de': "Deutsch",
                'zh': "简体中文", 'ru': "Русский", 'pt': "Português", 'it': "Italiano", 
                'ar': "العربية", 'tr': "Türkçe", 'ja': "日本語", 'ko': "한국어",
                'th': "ไทย", 'hi': "हिन्दी", 'vi': "Tiếng Việt", 'pl': "Polski",
                'nl': "Nederlands", 'sv': "Svenska", 'no': "Norsk", 'da': "Dansk",
                'fi': "Suomi", 'he': "עברית", 'cs': "Čeština", 'sk': "Slovenčina",
                'hu': "Magyar", 'ro': "Română", 'bg': "Български", 'hr': "Hrvatski"
            }
                
            lang_name = lang_names.get(lang_code, lang_code)
            confirmation = f"{get_text(lang_code, 'language_changed')} ({lang_name})"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"✅ {get_text(lang_code, 'begin_button')}",
                    callback_data="terms_accepted"
                )]
            ])
            
            await query.edit_message_text(confirmation, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Erreur dans set_language_callback: {e}")
            await query.edit_message_text("❌ Erreur de changement de langue")

    @staticmethod
    async def handle_main_start(update: Update, context: CallbackContext):
        try:
            user_id = update.effective_user.id
            
            if db.is_new_user(user_id):
                db.users[user_id] = {
                    'state': UserStates.INITIAL.value,
                    'language': 'fr',
                    'trial_end_date': (datetime.now() + timedelta(days=14)).isoformat()
                }
                db.save_to_disk('users', {str(user_id): db.users[user_id]})
                await show_language_selection(update)
            else:
                await show_main_menu(update, context)
        except Exception as e:
            logger.error(f"Erreur dans handle_main_start: {e} [ERR_BLM_004]", exc_info=True)
            await update.message.reply_text("❌ Erreur lors de l'initialisation. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_004)")

# Configuration terminée pour les 28 langues
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
    },
    'nl': {
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
    },
    'sv': {
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
    },
    'uk': {
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
    },
    'sw': {
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
    },
    'he': {
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
    },
    'ro': {
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
    },
    'fa': {
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
        "bot_info_title": "معلومات ربات",
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
        "change_language": "تغيير زبان",
        "manage_bots": "مديريت ربات‌ها",
        "help_command": "راهنما",
        "current_features": "ويژگی‌های فعلی",
        "multilingual_support": "پشتیبانی چندزبانه",
        "bot_management": "مديريت ربات",
        "user_preferences": "تنظیمات کاربر",
        "demo_mode": "حالت دمو فعال است",
        "welcome": "خوش آمدید! لطفاً زبان خود را انتخاب کنید:",
        "data_export": "خروجی گرفتن از داده‌ها"
    },
    'ms': {
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
    },
    'id': {
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
    
}

def get_text(lang: str, key: str) -> str:
    lang_data = TRANSLATIONS.get(lang, TRANSLATIONS['fr'])
    return lang_data.get(key, key)

async def handle_pdg_token_input(update: Update, context: CallbackContext, application):
    try:
        return application
    except Exception as e:
        logger.error(f"Erreur dans handle_pdg_token_input: {e} [ERR_BLM_037]", exc_info=True)
        await update.message.reply_text(
            "❌ Erreur lors de la configuration du Bot PDG. "
            "Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_037)"
        )


async def show_language_options(update: Update, context: CallbackContext):
        """Affiche le menu de sélection de langue avec 28 options"""
        try:
            # Récupération de l'utilisateur et de sa langue
            if update.message:
                user_id = update.message.from_user.id
                lang = db.get_user_language(user_id) or 'fr'
            else:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                lang = db.get_user_language(user_id) or 'fr'

            text = get_text(lang, 'language_selection')
            
            # Dictionnaire complet des 28 langues avec emojis
            lang_names = {
                'fr': "🇫🇷 Français",
                'en': "🇬🇧 English",
                'es': "🇪🇸 Español",
                'de': "🇩🇪 Deutsch",
                'zh': "🇨🇳 中文",
                'hi': "🇮🇳 हिन्दी",
                'ja': "🇯🇵 日本語",
                'ko': "🇰🇷 한국어",
                'th': "🇹🇭 ไทย",
                'ru': "🇷🇺 Русский",
                'pt': "🇵🇹 Português",
                'it': "🇮🇹 Italiano",
                'ar': "🇸🇦 العربية",
                'tr': "🇹🇷 Türkçe",
                'vi': "🇻🇳 Tiếng Việt",
                'pl': "🇵🇱 Polski",
                'nl': "🇳🇱 Nederlands",
                'sv': "🇸🇪 Svenska",
                'uk': "🇺🇦 Українська",
                'sw': "🇰🇪 Kiswahili",
                'he': "🇮🇱 עברית",
                'ro': "🇷🇴 Română",
                'fa': "🇮🇷 فارسی",
                'ms': "🇲🇾 Bahasa Melayu",
                'id': "🇮🇩 Bahasa Indonesia",
                'cs': "🇨🇿 Čeština",
                'da': "🇩🇰 Dansk",
                'fi': "🇫🇮 Suomi",
                'hu': "🇭🇺 Magyar"
            }

            # Création des boutons par groupe de 3
            buttons = []
            row = []
            
            for code, label in lang_names.items():
                row.append(InlineKeyboardButton(label, callback_data=f"setlang_{code}"))
                if len(row) == 3:  # 3 boutons par ligne
                    buttons.append(row)
                    row = []
            
            # Ajouter la dernière ligne si incomplète
            if row:
                buttons.append(row)

            # Bouton de retour
            buttons.append([
                InlineKeyboardButton(
                    get_text(lang, 'back_button'), 
                    callback_data="back_to_main"
                )
            ])

            markup = InlineKeyboardMarkup(buttons)

            # Envoi du message
            if update.message:
                await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
            else:
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Erreur dans show_language_options: {e} [ERR_LANG_OPT]", exc_info=True)
            error_msg = get_text(lang, 'error_try_again') if 'lang' in locals() else "An error occurred"
            if update.message:
                await update.message.reply_text(f"❌ {error_msg}")
            elif 'query' in locals():
                await query.edit_message_text(f"❌ {error_msg}")

    @staticmethod
    async def set_language_callback(update: Update, context: CallbackContext):
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
                'id': "Bahasa Indonesia",
                'cs': "Čeština",
                'da': "Dansk",
                'fi': "Suomi",
                'hu': "Magyar"
            }
                
            lang_name = lang_names.get(lang_code, lang_code)
            confirmation = f"{get_text(lang_code, 'language_changed')} ({lang_name})"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"✅ {get_text(lang_code, 'begin_button')}",
                    callback_data="terms_accepted"
                )]
            ])
            
            await query.edit_message_text(confirmation, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error in set_language_callback: {e}")
            await query.edit_message_text("❌ Language change error")

    # Fonction terms_declined ajoutée
    @staticmethod
    async def terms_declined(update: Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()
        lang = db.get_user_language(query.from_user.id) or 'fr'
        text = get_text(lang, 'terms_declined')
        await query.edit_message_text(text)

    @staticmethod
    async def accept_terms(update: Update, context: CallbackContext):
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            if lang == 'fr':
                terms_text = (
                    "📜 <b>Conditions d'utilisation</b>\n\n"
                    "1. Confidentialité : Vos données sont cryptées\n"
                    "2. Utilisation : Interdiction de spam\n"
                    "3. Sécurité : Ne partagez pas vos tokens\n\n"
                    "En continuant, vous acceptez nos conditions."
                )
            else:
                terms_text = (
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
            
            await query.edit_message_text(terms_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erreur dans accept_terms: {e} [ERR_BLM_007]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_007)")

    @staticmethod
    async def terms_accepted(update: Update, context: CallbackContext):
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
        try:
            if update.message:
                user_id = update.message.from_user.id
                lang = db.get_user_language(user_id) or 'fr'
            else:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                lang = db.get_user_language(user_id) or 'fr'
            
            if lang == 'fr':
                text = "🤖 Création de votre bot personnel\n\nAvez-vous déjà un bot Telegram existant ?"
            else:
                text = "🤖 Creating your bot assistant\n\nDo you already have an existing Telegram bot?"
            
            if update.message:
                await update.message.reply_text(text, reply_markup=KeyboardManager.bot_creation_options(lang))
            else:
                await query.edit_message_text(text, reply_markup=KeyboardManager.bot_creation_options(lang))
        except Exception as e:
            logger.error(f"Erreur dans start_bot_creation: {e} [ERR_BLM_009]", exc_info=True)
            if update.callback_query:
                await update.callback_query.message.reply_text("❌ Erreur lors du démarrage. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_009)")
            else:
                await update.message.reply_text("❌ Erreur lors du démarrage. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_009)")

    @staticmethod
    async def handle_has_token_yes(update: Update, context: CallbackContext):
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'

            if lang == 'fr':
                security_advice = (
                    "🔐 Conseil de sécurité :\n"
                    "1. Ne partagez jamais votre token publiquement\n"
                    "2. Utilisez /revoke dans @BotFather si compromis\n"
                    "3. Notre système le chiffrera automatiquement"
                )
                prompt = "Parfait ! Veuillez m'envoyer votre token :"
            else:
                security_advice = (
                    "🔐 Security advice:\n"
                    "1. Never share your token publicly\n"
                    "2. Use /revoke in @BotFather if compromised\n"
                    "3. Our system will encrypt it automatically"
                )
                prompt = "Perfect! Please send me your token:"
                
            await query.edit_message_text(f"✅ {prompt}\n\n{security_advice}", parse_mode="Markdown")
            context.user_data["awaiting_token"] = True
        except Exception as e:
            logger.error(f"Erreur dans handle_has_token_yes: {e} [ERR_BLM_010]", exc_info=True)
            await query.edit_message_text("❌ Erreur. Veuillez réessayer. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_010)")

    @staticmethod
    async def handle_has_token_no(update: Update, context: CallbackContext):
        try:
            query = update.callback_query
            await query.answer()
            lang = db.get_user_language(query.from_user.id) or 'fr'

            if lang == 'fr':
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
            else:
                creation_guide = (
                    "⚙️ Creating your first bot:\n\n"
                    "1. Open @BotFather\n"
                    "2. Send /newbot\n"
                    "3. Follow the instructions\n"
                    "4. Copy the generated token\n\n"
                    "⚠️ Security guidelines:\n"
                    "- NEVER share this token\n"
                    "- Change it immediately if compromised\n"
                    "- Our system will encrypt it automatically\n\n"
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

            bot_data = sync_validate_bot_token(token)
            if not bot_data:
                error_msg = "❌ Token invalide. Veuillez vérifier et réessayer." if lang == 'fr' else "❌ Invalid token. Please try again."
                await update.message.reply_text(error_msg)
                return

            bot_username = bot_data.get("username")
            bot_name = bot_data.get("first_name")
            
            bot_link = f"https://t.me/{bot_username}"
            creation_time = datetime.now().isoformat()
            db.save_user_bot(user_id, token, bot_username, bot_name, creation_time)

            try:
                child_app = init_child_bot(token, bot_username)
                if child_app:
                    from utils.user_features import setup_user_bot_handlers
                    await setup_user_bot_handlers(child_app)                    
                    import asyncio
                    await child_app.initialize()
                    await child_app.start()
                    asyncio.create_task(child_app.updater.start_polling())
            
                if lang == 'fr':
                    success_text = (
                        f"✅ Bot @{bot_username} connecté avec succès !\n\n"
                        f"Vous pouvez maintenant utiliser votre bot : {bot_link}\n\n"
                        f"N'oubliez pas de consulter votre plan pour les limites et fonctionnalités : /planinfo"
                    )
                else:
                    success_text = (
                        f"✅ Bot @{bot_username} successfully connected!\n\n"
                        f"You can now use your bot: {bot_link}\n\n"
                        f"Don't forget to check your plan for limits and features: /planinfo"
                    )
                
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🤖 Aller à votre bot" if lang == 'fr' else "🤖 Go to your bot", url=bot_link),
                        InlineKeyboardButton("📊 Mon plan" if lang == 'fr' else "📊 My plan", callback_data="show_plan_info")
                    ]
                ])

                await update.message.reply_text(success_text, reply_markup=keyboard, parse_mode="HTML")
                context.user_data["awaiting_token"] = False

            except Exception as e:
                logger.error(f"Erreur lors du lancement du bot enfant: {e}")
                await update.message.reply_text(f"❌ Erreur lors du lancement du bot enfant: {e}")

        except Exception as e:
            logger.error(f"ERREUR: {str(e)}", exc_info=True)
            await update.message.reply_text("❌ Erreur lors du traitement")
            context.user_data["awaiting_token"] = False

    # ... (continuer avec les autres méthodes en suivant le même modèle)
    
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
            else:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            
            if lang == 'fr':
                text = "🛠️ <b>Services disponibles</b> :"
            else:
                text = "🛠️ <b>Available Services</b>:"
            
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
        
        if lang == 'fr':
            text = "🚧 Fonctionnalité en cours de construction"
        else:
            text = "🚧 Feature under construction"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Retour" if lang == 'fr' else "🔙 Back", callback_data="back_to_services")]
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
            else:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'

            if lang == 'fr':
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
            )
            else:
                help_text = (
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
            
            if lang == 'fr':
                text = "💎 <b>Choisissez un plan</b>\n\n"
            else:
                text = "💎 <b>Choose a plan</b>\n\n"
            
            keyboard = []
            for plan_id, plan_data in PLANS.items():
                features_text = "\n".join([f"• {f}" for f in plan_data["features"]])
                text += (
                    f"{plan_data['label']} ({plan_data['price']})\n"
                    f"{features_text}\n\n"
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
            if lang == 'fr':
                error_msg = "❌ Erreur d'affichage des plans. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_018)"
            else:
                error_msg = "❌ Error displaying plans. Contact support (@TeleSucheSupport) if the problem persists. (ERR_BLM_018)"
            await query.edit_message_text(error_msg)

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
            if lang == 'fr':
                await query.edit_message_text("🎉 Félicitations ! Votre compte a été upgradé.")
            else:
                await query.edit_message_text("🎉 Congratulations! Your account has been upgraded.")
            # Envoyer un message avec les nouvelles limites
            await BotLinkingManager.show_plan_info(update, context)
        else:
            if lang == 'fr':
                await query.edit_message_text("❌ Échec du paiement. Veuillez réessayer.")
            else:
                await query.edit_message_text("❌ Payment failed. Please try again.")

    except Exception as e:
        logger.error(f"Erreur dans handle_confirm_upgrade: {e} [ERR_BLM_019]", exc_info=True)
        if lang == 'fr':
            error_msg = "❌ Erreur lors de la mise à niveau. Contactez le support (@TeleSucheSupport) si le problème persiste. (ERR_BLM_019)"
        else:
            error_msg = "❌ Upgrade error. Contact support (@TeleSucheSupport) if the problem persists. (ERR_BLM_019)"
        await query.edit_message_text(error_msg)

    @staticmethod
    async def show_plan_info(update: Update, context: CallbackContext):
    """Affiche les informations du plan actuel"""
    try:
        if update.message:
            user_id = update.message.from_user.id
        else:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            
        lang = db.get_user_language(user_id) or 'fr'
        plan = get_user_plan(user_id)
        plan_data = PLANS.get(plan, PLANS["free"])
        plan_limits = get_plan_limits(plan)
        
        user_bots = db.get_user_bots(user_id)
        bot_count = len(user_bots)
        
        if lang == 'fr':
            text = (
                f"💎 <b>Plan actuel : {plan_data['label']}</b>\n\n"
                f"📊 <b>Utilisation :</b>\n"
                f"• Bots : {bot_count}/{plan_limits['bots']}\n"
                f"• Groupes : 0/{plan_limits['groups']}\n\n"
                f"<b>Fonctionnalités :</b>\n"
            )
        else:
            text = (
                f"💎 <b>Current plan: {plan_data['label']}</b>\n\n"
                f"📊 <b>Usage:</b>\n"
                f"• Bots: {bot_count}/{plan_limits['bots']}\n"
                f"• Groups: 0/{plan_limits['groups']}\n\n"
                f"<b>Features:</b>\n"
            )
        
        for feature in plan_data["features"]:
            text += f"• {feature}\n"
            
        if plan == "free":
            if lang == 'fr':
                text += f"\n💡 <b>Upgradez pour plus de fonctionnalités !</b>"
            else:
                text += f"\n💡 <b>Upgrade for more features!</b>"
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
        else:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            
        lang = db.get_user_language(user_id) or 'fr'
        
        if lang == 'fr':
            text = (
                "🤝 <b>Rejoignez notre communauté !</b>\n\n"
                "Connectez-vous avec d'autres utilisateurs, partagez vos expériences et obtenez de l'aide."
            )
        else:
            text = (
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
            if lang == 'fr':
                await query.edit_message_text("❌ Bot non trouvé")
            else:
                await query.edit_message_text("❌ Bot not found")
            return
            
        bot_username = selected_bot.get("bot_username", "Unknown")
        
        if lang == 'fr':
            text = (
                f"⚠️ <b>Supprimer le bot</b>\n\n"
                f"🤖 @{bot_username}\n\n"
                f"Cette action est irréversible. Êtes-vous sûr ?"
            )
        else:
            text = (
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
            
            if lang == 'fr':
                text = f"✅ Bot supprimé avec succès !"
            else:
                text = f"✅ Bot deleted successfully!"
        else:
            if lang == 'fr':
                text = f"❌ Erreur lors de la suppression"
            else:
                text = f"❌ Error during deletion"
        
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

        text = f"<b>{get_text(lang, 'bot_token')}</b>\n\n<code>{bot_token}</code>"
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
    
    text = "🚧 Fonctionnalité en cours de construction" if lang == 'fr' else "🚧 Feature under construction"
    
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
                dt = datetime.fromisoformat(creation_time)
                creation_date = dt.strftime("%Y-%m-%d")
                creation_time_formatted = dt.strftime("%H:%M:%S")
            except:
                creation_date = "2025-07-21"
                creation_time_formatted = "17:33:59"
        else:
            creation_date = "2025-07-21"
            creation_time_formatted = "17:33:59"

        if lang == 'fr':
            text = (
                f"<b>{get_text(lang, 'bot_info_title')}</b>\n\n"
                f"<b>Nom</b> : {bot_name}\n"
                f"<b>Username</b> : @{bot_username}\n"
                f"<b>ID</b> : N/A\n"
                f"<b>Date de création</b> : \n"
                f"  ├📆 {creation_date} \n"
                f"  └🕑{creation_time_formatted}.\n\n"
                f"<b>Statistiques</b>\n\n"
                f"{get_text(lang, 'earnings')}\n"
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
                f"  {get_text(lang, 'monetization')}\n"
                f"  └ {get_text(lang, 'monetization_active')}\n\n"
                f"   {get_text(lang, 'files')} : \n"
                f"  └ 2.500.000 fichiers\n\n"
                f"------\n"
                f"{get_text(lang, 'bot_token_security')}"
            )
        else:
            text = (
                f"<b>{get_text(lang, 'bot_info_title')}</b>\n\n"
                f"<b>Name</b> : {bot_name}\n"
                f"<b>Username</b> : @{bot_username}\n"
                f"<b>ID</b> : N/A\n"
                f"<b>Creation date</b> : \n"
                f"  ├📆 {creation_date} \n"
                f"  └🕑{creation_time_formatted}.\n\n"
                f"<b>Statistics</b>\n\n"
                f"{get_text(lang, 'earnings')}\n"
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
                f"  {get_text(lang, 'monetization')}\n"
                f"  └ {get_text(lang, 'monetization_active')}\n\n"
                f"   {get_text(lang, 'files')} : \n"
                f"  └ 2,500,000 files\n\n"
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
        else:
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
        if lang == 'fr':
            text = (
                f"<b>{get_text(lang, 'add_bot_token')}</b>\n\n"
                f"{get_text(lang, 'enter_token')}\n\n"
                f"<i>{get_text(lang, 'token_format')}</i>"
            )
        else:
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
        
        if lang == 'fr':
            text = (
                f"<b>{get_text(lang, 'delete_confirmation')}</b>\n\n"
                f"🤖 @{bot_username}\n\n"
                f"⚠️ {get_text(lang, 'this_action_irreversible')}"
            )
        else:
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
        
        if lang == 'fr':
            text = (
                f"⏰ {get_text(lang, 'delete_scheduled')}\n\n"
                f"🤖 @{bot_username}\n"
                f"🕐 {deletion_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Vous pouvez annuler cette suppression avant cette date."
            )
        else:
            text = (
                f"⏰ {get_text(lang, 'delete_scheduled')}\n\n"
                f"🤖 @{bot_username}\n"
                f"🕐 {deletion_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"You can cancel this deletion before this date."
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
        
        if lang == 'fr':
            text = f"✅ {get_text(lang, 'deletion_cancelled')}\n🤖 @{bot_username}"
        else:
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
        
        if lang == 'fr':
            text = (
                f"<b>🤖 {bot_name}</b>\n"
                f"<b>Username:</b> @{bot_username}\n"
                f"<b>Status:</b> {bot_status} {get_text(lang, 'bot_status_online' if bot_status == '🟢' else 'bot_status_offline')}\n\n"
                f"<b>Gestion:</b>"
            )
        else:
            text = (
                f"<b>🤖 {bot_name}</b>\n"
                f"<b>Username:</b> @{bot_username}\n"
                f"<b>Status:</b> {bot_status} {get_text(lang, 'bot_status_online' if bot_status == '🟢' else 'bot_status_offline')}\n\n"
                f"<b>Management:</b>"
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
                child_bots[bot_username] = bot_app
                try:
                    await bot_app.initialize()
                    await bot_app.start()
                    import asyncio
                    asyncio.create_task(bot_app.updater.start_polling())
                    text = f"✅ {get_text(lang, 'start_bot_success')}\n🤖 @{bot_username}"
                except Exception as e:
                    logger.error(f"Erreur démarrage bot: {e}")
                    text = f"❌ {get_text(lang, 'start_bot_error')}\n🤖 @{bot_username}"
            else:
                text = f"❌ {get_text(lang, 'start_bot_error')}\n🤖 @{bot_username}"
        else:
            text = f"ℹ️ {get_text(lang, 'bot_status_online')}\n🤖 @{bot_username}"
        
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
                await app.shutdown()
                del child_bots[bot_username]
                text = f"✅ {get_text(lang, 'stop_child_bot')}\n🤖 @{bot_username}"
            except Exception as e:
                logger.error(f"Erreur arrêt bot {bot_username}: {e}")
                text = f"❌ {get_text(lang, 'start_bot_error')}\n🤖 @{bot_username}"
        else:
            text = f"ℹ️ {get_text(lang, 'bot_status_offline')}\n🤖 @{bot_username}"

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
                await app.shutdown()
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
                child_bots[bot_username] = bot_app
                try:
                    await bot_app.initialize()
                    await bot_app.start()
                    import asyncio
                    asyncio.create_task(bot_app.updater.start_polling())
                    text = f"✅ {get_text(lang, 'restart_child_bot')}\n🤖 @{bot_username}"
                except Exception as e:
                    logger.error(f"Erreur démarrage bot: {e}")
                    text = f"❌ {get_text(lang, 'start_bot_error')}\n🤖 @{bot_username}"
            else:
                text = f"❌ {get_text(lang, 'start_bot_error')}\n🤖 @{bot_username}"
        else:
            text = f"❌ {get_text(lang, 'bot_not_found')}"
        
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

        # Statistiques simulées
        if lang == 'fr':
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
        else:
            text = (
                f"<b>📊 {get_text(lang, 'bot_analytics')}</b>\n"
                f"🤖 @{bot_username}\n\n"
                f"<b>📈 Last 24h:</b>\n"
                f"👥 New users: 156\n"
                f"💬 Messages received: 2,847\n"
                f"📤 Messages sent: 3,012\n\n"
                f"<b>📊 Last 7 days:</b>\n"
                f"👥 Active users: 1,245\n"
                f"💬 Total messages: 18,934\n"
                f"⚡ Average response time: 0.3s\n\n"
                f"<b>🎯 Performance:</b>\n"
                f"✅ Availability: 99.8%\n"
                f"📈 Growth: +12%\n"
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

        # Logs simulés
        if lang == 'fr':
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
        else:
            text = (
                f"<b>📜 {get_text(lang, 'bot_logs')}</b>\n"
                f"🤖 @{bot_username}\n\n"
                f"<code>2025-01-23 14:30:25 [INFO] Bot started</code>\n"
                f"<code>2025-01-23 14:30:26 [INFO] Handlers registered</code>\n"
                f"<code>2025-01-23 14:30:27 [INFO] Polling started</code>\n"
                f"<code>2025-01-23 14:35:12 [INFO] New user: 123456</code>\n"
                f"<code>2025-01-23 14:36:45 [INFO] Message processed: /start</code>\n"
                f"<code>2025-01-23 14:37:23 [WARN] Rate limit reached</code>\n"
                f"<code>2025-01-23 14:38:01 [INFO] Message processed: /help</code>\n"
                f"<code>2025-01-23 14:39:15 [ERROR] API error: Timeout</code>\n"
                f"<code>2025-01-23 14:40:22 [INFO] Connection restored</code>\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Télécharger logs" if lang == 'fr' else "📥 Download logs", callback_data=f"download_logs:{bot_username}")],
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
        
        # Créer les boutons de langue
        language_buttons = [
    [InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang:fr"),
     InlineKeyboardButton("🇬🇧 English", callback_data="set_lang:en"),
     InlineKeyboardButton("🇪🇸 Español", callback_data="set_lang:es")],
     
    [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang:de"),
     InlineKeyboardButton("🇨🇳 中文", callback_data="set_lang:zh"),
     InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="set_lang:hi")],
     
    [InlineKeyboardButton("🇯🇵 日本語", callback_data="set_lang:ja"),
     InlineKeyboardButton("🇰🇷 한국어", callback_data="set_lang:ko"),
     InlineKeyboardButton("🇹🇭 ไทย", callback_data="set_lang:th")],
     
    [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang:ru"),
     InlineKeyboardButton("🇵🇹 Português", callback_data="set_lang:pt"),
     InlineKeyboardButton("🇮🇹 Italiano", callback_data="set_lang:it")],
     
    [InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang:ar"),
     InlineKeyboardButton("🇹🇷 Türkçe", callback_data="set_lang:tr"),
     InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="set_lang:vi")],
     
    [InlineKeyboardButton("🇵🇱 Polski", callback_data="set_lang:pl"),
     InlineKeyboardButton("🇳🇱 Nederlands", callback_data="set_lang:nl"),
     InlineKeyboardButton("🇸🇪 Svenska", callback_data="set_lang:sv")],
     
    [InlineKeyboardButton("🇺🇦 Українська", callback_data="set_lang:uk"),
     InlineKeyboardButton("🇰🇪 Kiswahili", callback_data="set_lang:sw"),
     InlineKeyboardButton("🇮🇱 עברית", callback_data="set_lang:he")],
     
    [InlineKeyboardButton("🇷🇴 Română", callback_data="set_lang:ro"),
     InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang:fa"),
     InlineKeyboardButton("🇲🇾 Bahasa Melayu", callback_data="set_lang:ms")],
     
    [InlineKeyboardButton("🇮🇩 Bahasa Indonesia", callback_data="set_lang:id"),
     InlineKeyboardButton("🇨🇿 Čeština", callback_data="set_lang:cs"),
     InlineKeyboardButton("🇩🇰 Dansk", callback_data="set_lang:da")],
     
    [InlineKeyboardButton("🇫🇮 Suomi", callback_data="set_lang:fi"),
     InlineKeyboardButton("🇭🇺 Magyar", callback_data="set_lang:hu")],
     
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
            else:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                
            lang = db.get_user_language(user_id) or 'fr'
            
            if lang == 'fr':
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
            else:
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
     InlineKeyboardButton("🇬🇧 English", callback_data="set_lang:en"),
     InlineKeyboardButton("🇪🇸 Español", callback_data="set_lang:es")],
     
    [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang:de"),
     InlineKeyboardButton("🇨🇳 中文", callback_data="set_lang:zh"),
     InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="set_lang:hi")],
     
    [InlineKeyboardButton("🇯🇵 日本語", callback_data="set_lang:ja"),
     InlineKeyboardButton("🇰🇷 한국어", callback_data="set_lang:ko"),
     InlineKeyboardButton("🇹🇭 ไทย", callback_data="set_lang:th")],
     
    [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang:ru"),
     InlineKeyboardButton("🇵🇹 Português", callback_data="set_lang:pt"),
     InlineKeyboardButton("🇮🇹 Italiano", callback_data="set_lang:it")],
     
    [InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang:ar"),
     InlineKeyboardButton("🇹🇷 Türkçe", callback_data="set_lang:tr"),
     InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="set_lang:vi")],
     
    [InlineKeyboardButton("🇵🇱 Polski", callback_data="set_lang:pl"),
     InlineKeyboardButton("🇳🇱 Nederlands", callback_data="set_lang:nl"),
     InlineKeyboardButton("🇸🇪 Svenska", callback_data="set_lang:sv")],
     
    [InlineKeyboardButton("🇺🇦 Українська", callback_data="set_lang:uk"),
     InlineKeyboardButton("🇰🇪 Kiswahili", callback_data="set_lang:sw"),
     InlineKeyboardButton("🇮🇱 עברית", callback_data="set_lang:he")],
     
    [InlineKeyboardButton("🇷🇴 Română", callback_data="set_lang:ro"),
     InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang:fa"),
     InlineKeyboardButton("🇲🇾 Bahasa Melayu", callback_data="set_lang:ms")],
     
    [InlineKeyboardButton("🇮🇩 Bahasa Indonesia", callback_data="set_lang:id"),
     InlineKeyboardButton("🇨🇿 Čeština", callback_data="set_lang:cs"),
     InlineKeyboardButton("🇩🇰 Dansk", callback_data="set_lang:da")],
     
    [InlineKeyboardButton("🇫🇮 Suomi", callback_data="set_lang:fi"),
     InlineKeyboardButton("🇭🇺 Magyar", callback_data="set_lang:hu")],
     
    [InlineKeyboardButton(get_text(current_lang, 'back_button'), callback_data="back_to_main")]
]
                
                keyboard = InlineKeyboardMarkup(language_buttons)
                await update.message.reply_text(text, reply_markup=keyboard)
            else:
                # Utilisateur existant - menu principal
                await show_main_menu(update, context)
                
        except Exception as e:
            logger.error(f"Erreur dans welcome_message: {e} [ERR_BLM_017]", exc_info=True)
            await update.message.reply_text(f"{get_text(lang, 'error_try_again')} (ERR_BLM_017)")

    @staticmethod
async def handle_open_menu(update: Update, context: CallbackContext):
        """Handler pour le bouton 'Ouvrir' du menu principal"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            # Réutilise la logique de bienvenue
            if db.is_new_user(user_id):
                text = get_text(lang, 'welcome')
                
                language_buttons = [
    [InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang:fr"),
     InlineKeyboardButton("🇬🇧 English", callback_data="set_lang:en"),
     InlineKeyboardButton("🇪🇸 Español", callback_data="set_lang:es")],
     
    [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang:de"),
     InlineKeyboardButton("🇨🇳 中文", callback_data="set_lang:zh"),
     InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="set_lang:hi")],
     
    [InlineKeyboardButton("🇯🇵 日本語", callback_data="set_lang:ja"),
     InlineKeyboardButton("🇰🇷 한국어", callback_data="set_lang:ko"),
     InlineKeyboardButton("🇹🇭 ไทย", callback_data="set_lang:th")],
     
    [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang:ru"),
     InlineKeyboardButton("🇵🇹 Português", callback_data="set_lang:pt"),
     InlineKeyboardButton("🇮🇹 Italiano", callback_data="set_lang:it")],
     
    [InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang:ar"),
     InlineKeyboardButton("🇹🇷 Türkçe", callback_data="set_lang:tr"),
     InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="set_lang:vi")],
     
    [InlineKeyboardButton("🇵🇱 Polski", callback_data="set_lang:pl"),
     InlineKeyboardButton("🇳🇱 Nederlands", callback_data="set_lang:nl"),
     InlineKeyboardButton("🇸🇪 Svenska", callback_data="set_lang:sv")],
     
    [InlineKeyboardButton("🇺🇦 Українська", callback_data="set_lang:uk"),
     InlineKeyboardButton("🇰🇪 Kiswahili", callback_data="set_lang:sw"),
     InlineKeyboardButton("🇮🇱 עברית", callback_data="set_lang:he")],
     
    [InlineKeyboardButton("🇷🇴 Română", callback_data="set_lang:ro"),
     InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang:fa"),
     InlineKeyboardButton("🇲🇾 Bahasa Melayu", callback_data="set_lang:ms")],
     
    [InlineKeyboardButton("🇮🇩 Bahasa Indonesia", callback_data="set_lang:id"),
     InlineKeyboardButton("🇨🇿 Čeština", callback_data="set_lang:cs"),
     InlineKeyboardButton("🇩🇰 Dansk", callback_data="set_lang:da")],
     
    [InlineKeyboardButton("🇫🇮 Suomi", callback_data="set_lang:fi"),
     InlineKeyboardButton("🇭🇺 Magyar", callback_data="set_lang:hu")],
     
    [InlineKeyboardButton(get_text(current_lang, 'back_button'), callback_data="back_to_main")]
]
                ]
                
                keyboard = InlineKeyboardMarkup(language_buttons)
                await query.edit_message_text(text, reply_markup=keyboard)
            else:
                # Utilisateur existant - menu principal
                await show_main_menu(update, context)
        except Exception as e:
            logger.error(f"Erreur dans handle_open_menu: {e} [ERR_BLM_018]", exc_info=True)
            await query.edit_message_text(f"❌ Erreur. Veuillez réessayer. (ERR_BLM_018)")

    @staticmethod
    async def handle_info_menu(update: Update, context: CallbackContext):
        """Handler pour le bouton 'Infos' du menu principal"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            if lang == 'fr':
                info_text = (
                    "🤖 <b>TeleSucheBot - Votre assistant multifonction</b>\n\n"
                    "TeleSucheBot est un projet innovant de recherche sur Telegram, conçu pour offrir une multitude de services avancés. "
                    "Notre objectif est de fournir un outil polyvalent qui répond à tous vos besoins en matière de communication, d'automatisation et de gestion de contenu.\n\n"
                    "<b>Fonctionnalités principales :</b>\n"
                    "• 🤖 <b>Création de bots personnels</b> : Clonez votre propre bot et personnalisez-le selon vos besoins\n"
                    "• 🌐 <b>Support multilingue</b> : Disponible dans plus de 20 langues différentes\n"
                    "• 🔍 <b>Recherche avancée</b> : Trouvez des informations rapidement grâce à notre moteur de recherche puissant\n"
                    "• 💬 <b>Gestion de groupes et de canaux</b> : Outils de modération et d'analyse complets\n"
                    "• 📊 <b>Statistiques détaillées</b> : Suivez les performances de vos bots avec des métriques précises\n"
                    "• 🛠️ <b>Services divers</b> : Conversion de fichiers, synthèse vocale, création de sondages, et bien plus\n\n"
                    "Ce projet est en constante évolution, avec de nouvelles fonctionnalités ajoutées régulièrement. "
                    "Rejoignez notre communauté pour contribuer et bénéficier des dernières avancées !\n\n"
                    "📚 Pour en savoir plus :\n"
                    "👉 https://telegra.ph/TeleSucheBot-Project-07-26"
                )
            else:
                info_text = (
                    "🤖 <b>TeleSucheBot - Your Multifunctional Assistant</b>\n\n"
                    "TeleSucheBot is an innovative research project on Telegram, designed to provide a multitude of advanced services. "
                    "Our goal is to deliver a versatile tool that meets all your communication, automation, and content management needs.\n\n"
                    "<b>Main features:</b>\n"
                    "• 🤖 <b>Personal bot creation</b>: Clone your own bot and customize it to your needs\n"
                    "• 🌐 <b>Multilingual support</b>: Available in more than 20 languages\n"
                    "• 🔍 <b>Advanced search</b>: Find information quickly with our powerful search engine\n"
                    "• 💬 <b>Group and channel management</b>: Comprehensive moderation and analytics tools\n"
                    "• 📊 <b>Detailed statistics</b>: Track your bots' performance with precise metrics\n"
                    "• 🛠️ <b>Various services</b>: File conversion, text-to-speech, poll creation, and much more\n\n"
                    "This project is constantly evolving, with new features added regularly. "
                    "Join our community to contribute and benefit from the latest advancements!\n\n"
                    "📚 Learn more:\n"
                    "👉 https://telegra.ph/TeleSucheBot-Project-07-26"
                )
            
            await query.edit_message_text(
                info_text,
                reply_markup=KeyboardManager.info_menu(lang),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_info_menu: {e} [ERR_BLM_019]", exc_info=True)
            await query.edit_message_text(f"❌ Erreur. Veuillez réessayer. (ERR_BLM_019)")

    @staticmethod
async def handle_config_menu(update: Update, context: CallbackContext):
        """Handler pour le bouton 'Config' du menu principal"""
        try:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            text = "⚙️ <b>Configuration de votre compte</b>\n\nChoisissez une option à modifier :"
            await query.edit_message_text(
                text,
                reply_markup=KeyboardManager.config_menu(lang),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Erreur dans handle_config_menu: {e} [ERR_BLM_020]", exc_info=True)
            await query.edit_message_text(f"❌ Erreur. Veuillez réessayer. (ERR_BLM_020)")

    @staticmethod
    async def handle_config_option(update: Update, context: CallbackContext):
        """Handler pour les options de configuration"""
        try:
            query = update.callback_query
            await query.answer()
            option = query.data
            user_id = query.from_user.id
            lang = db.get_user_language(user_id) or 'fr'
            
            if option == 'config_name':
                prompt = "Entrez votre nouveau nom :" if lang == 'fr' else "Enter your new name:"
                context.user_data['awaiting_name'] = True
            elif option == 'config_country':
                prompt = "Sélectionnez votre pays :" if lang == 'fr' else "Select your country:"
                # Implémenter la logique de sélection de pays
            elif option == 'config_phone':
                prompt = "Partagez votre numéro de téléphone :" if lang == 'fr' else "Share your phone number:"
                context.user_data['awaiting_phone'] = True
            elif option == 'config_location':
                prompt = "Partagez votre localisation :" if lang == 'fr' else "Share your location:"
                context.user_data['awaiting_location'] = True
                
            await query.edit_message_text(prompt)
        except Exception as e:
            logger.error(f"Erreur dans handle_config_option: {e} [ERR_BLM_021]", exc_info=True)
            await query.edit_message_text(f"❌ Erreur. Veuillez réessayer. (ERR_BLM_021)")
    

def setup_bot_linking_handlers(application: Application):
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
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_open_menu, pattern="^open_menu$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_info_menu, pattern="^info_menu$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_config_menu, pattern="^config_menu$"))
    application.add_handler(CallbackQueryHandler(BotLinkingManager.handle_config_option, pattern="^config_"))

    application.add_handler(CommandHandler("start", BotLinkingManager.welcome_message))
    application.add_handler(CommandHandler("mybots", BotLinkingManager.handle_my_bots))
    application.add_handler(CommandHandler("lang", BotLinkingManager.language_selection_menu))
    application.add_handler(CommandHandler("help", BotLinkingManager.help_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, BotLinkingManager.handle_token_input))
    
    logger.info("Bot linking handlers configurés avec succès")

def setup(application: Application):
    setup_bot_linking_handlers(application)
    logger.info("Handlers de BotLinking configurés")

async def cleanup_pending_deletions():
    try:
        await BotLinkingManager.execute_pending_deletions()
    except Exception as e:
        logger.error(f"Erreur cleanup_pending_deletions: {e}")

async def start_bot_linking_system():
    try:
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
                            child_bots[bot_username] = bot_app
                            await bot_app.initialize()
                            await bot_app.start()
                            import asyncio
                            asyncio.create_task(bot_app.updater.start_polling())
                    except Exception as e:
                        logger.error(f"Erreur démarrage bot {bot_username}: {e}")
        logger.info(f"Système de gestion des bots démarré - {len(child_bots)} bots actifs")
    except Exception as e:
        logger.error(f"Erreur démarrage système bot linking: {e}")

def setup(application: Application):
    """Configure les handlers pour la gestion des bots"""
    setup_bot_linking_handlers(application)
    logger.info("Handlers de BotLinking configurés")

async def main():
    try:
        BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
        
        if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("⚠️  Veuillez configurer votre token de bot dans la variable BOT_TOKEN")
            print("💡 Obtenez votre token depuis @BotFather sur Telegram")
            return
        
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        setup_handlers(application)
        await start_bot_linking_system()
        
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

