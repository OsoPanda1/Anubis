from telethon import TelegramClient, events, functions, types
from telethon.tl.types import PeerUser, PeerChannel, PeerChat, ChannelParticipantsAdmins, User
from telethon.errors import UserNotMutualContactError, ChatAdminRequiredError
import sqlite3
from datetime import datetime
import logging
from typing import Union, Optional

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("anubis.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuración de credenciales
API_ID = '21138709'
API_HASH = 'b988f0a873745ace76cd7a47f5f3e4d9'
PHONE = '+527712132427'
BOT_USERNAME = '@Slut_killerbot'

# Configuración de seguridad
OWNER_ID = 123456789  # Reemplaza con tu ID de Telegram
AUTHORIZED_ADMINS = [OWNER_ID]

# Inicializar cliente
client = TelegramClient(BOT_USERNAME, API_ID, API_HASH)

# Configuración de la base de datos
class Database:
    def __init__(self, db_name: str = 'userbot.db'):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        """Configura todas las tablas necesarias en la base de datos"""
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                ban_date TEXT,
                reason TEXT,
                banned_by INTEGER,
                chat_id INTEGER,
                evidence TEXT
            );
            CREATE TABLE IF NOT EXISTS muted_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                mute_date TEXT,
                muted_by INTEGER,
                chat_id INTEGER,
                duration INTEGER,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS user_info (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TEXT,
                last_seen TEXT,
                message_count INTEGER DEFAULT 0,
                warn_count INTEGER DEFAULT 0,
                notes TEXT,
                status TEXT,
                profile_pics INTEGER DEFAULT 0,
                is_bot BOOLEAN,
                is_verified BOOLEAN,
                is_restricted BOOLEAN,
                is_scam BOOLEAN,
                lang_code TEXT
            );
            CREATE TABLE IF NOT EXISTS authorized_admins (
                admin_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_date TEXT,
                permissions TEXT,
                active BOOLEAN DEFAULT TRUE
            );
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                welcome_message TEXT,
                rules TEXT,
                antiflood_settings TEXT,
                blocked_words TEXT,
                language TEXT DEFAULT 'es',
                protection_enabled BOOLEAN DEFAULT TRUE
            );
            CREATE TABLE IF NOT EXISTS user_actions (
                action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                admin_id INTEGER,
                action_type TEXT,
                action_date TEXT,
                chat_id INTEGER,
                reason TEXT,
                duration INTEGER,
                evidence TEXT
            );
            CREATE TABLE IF NOT EXISTS button_config (
                chat_id INTEGER PRIMARY KEY,
                message TEXT,
                photo_id TEXT,
                gif_id TEXT,
                video_id TEXT,
                hours TEXT,
                buttons TEXT,
                timezone TEXT
            );
        ''')
        self.conn.commit()

    def close(self):
        """Cierra la conexión a la base de datos"""
        self.conn.close()

# Inicializar base de datos
db = Database()

# Clases de utilidad
class SecurityCheck:
    @staticmethod
    async def is_admin(event, user_id: int) -> bool:
        """Verifica si un usuario es administrador"""
        try:
            chat = await event.get_chat()
            if user_id in AUTHORIZED_ADMINS:
                return True
            if hasattr(chat, 'admin_rights'):
                admins = await client.get_participants(chat, filter=ChannelParticipantsAdmins)
                return any(admin.id == user_id for admin in admins)
            return False
        except Exception as e:
            logger.error(f"Error verificando admin: {e}")
            return False

    @staticmethod
    def require_admin():
        """Decorador para requerir permisos de administrador"""
        def decorator(func):
            async def wrapper(event):
                try:
                    sender = await event.get_sender()
                    if not await SecurityCheck.is_admin(event, sender.id):
                        await event.respond("⛔ No tienes permiso para usar este comando.")
                        return
                    return await func(event)
                except Exception as e:
                    logger.error(f"Error en decorador admin: {e}")
                    await event.respond("❌ Error al verificar permisos.")
            return wrapper
        return decorator

class UserManager:
    @staticmethod
    async def get_full_user_info(user_id: int) -> dict:
        """Obtiene información completa de un usuario"""
        try:
            user = await client.get_entity(user_id)
            db.cursor.execute('SELECT * FROM user_info WHERE user_id = ?', (user_id,))
            user_data = db.cursor.fetchone()
            
            full_info = {
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': getattr(user, 'phone', None),
                'bot': user.bot,
                'verified': user.verified,
                'restricted': user.restricted,
                'scam': user.scam,
                'message_count': user_data[6] if user_data else 0,
                'warn_count': user_data[7] if user_data else 0,
                'notes': user_data[8] if user_data else None,
                'first_seen': user_data[4] if user_data else None,
                'last_seen': user_data[5] if user_data else None
            }
            return full_info
        except Exception as e:
            logger.error(f"Error obteniendo info de usuario: {e}")
            return None

    @staticmethod
    async def track_user_action(user_id: int, admin_id: int, action_type: str, chat_id: int, reason: str = None, duration: int = None, evidence: str = None):
        """Registra una acción administrativa sobre un usuario"""
        try:
            db.cursor.execute('''
                INSERT INTO user_actions (
                    user_id, admin_id, action_type, action_date, 
                    chat_id, reason, duration, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, admin_id, action_type, datetime.now().isoformat(),
                  chat_id, reason, duration, evidence))
            db.conn.commit()
        except Exception as e:
            logger.error(f"Error registrando acción: {e}")

# Funciones de utilidad
async def find_user(event, user_reference: Union[str, int]) -> Optional[User]:
    """Encuentra un usuario por diferentes referencias"""
    try:
        if isinstance(user_reference, str):
            if user_reference.isdigit():
                return await client.get_entity(int(user_reference))
            elif user_reference.startswith('@'):
                return await client.get_entity(user_reference)
            else:
                return await client.get_entity(f"@{user_reference}")
        elif isinstance(user_reference, int):
            return await client.get_entity(user_reference)
        return None
    except Exception as e:
        logger.error(f"Error encontrando usuario: {e}")
        return None

async def get_target_user(event) -> Optional[User]:
    """Obtiene el usuario objetivo de un comando"""
    try:
        if event.reply_to_msg_id:
            reply_msg = await event.get_reply_message()
            return await client.get_entity(reply_msg.sender_id)
        else:
            args = event.raw_text.split(maxsplit=1)
            if len(args) > 1:
                return await find_user(event, args[1].strip())
        return None
    except Exception as e:
        logger.error(f"Error obteniendo usuario objetivo: {e}")
        return None

# Comandos básicos
@client.on(events.NewMessage(pattern=r'[\.!/]start'))
async def start_cmd(event):
    """Comando de inicio"""
    try:
        start_message = """
🔱 **ANUBIS USERBOT MEJORADO** 🔱

¡Bienvenido al sistema de moderación más seguro y poderoso!

**Ironblood Anubis** ahora cuenta con:
• Sistema de permisos avanzado
• Tracking de usuarios detallado
• Registro de acciones administrativas
• Protección contra spam y flood
• Sistema de notas y advertencias
• Estadísticas detalladas

Para ver todos los comandos disponibles usa /help

Desarrollado por: @Ironblood_Anubis
        """
        await event.respond(start_message)
    except Exception as e:
        logger.error(f"Error en comando start: {e}")

@client.on(events.NewMessage(pattern=r'[\.!/]help'))
async def help_cmd(event):
    """Comando de ayuda"""
    try:
        help_message = """
📚 **COMANDOS DE ANUBIS USERBOT** 📚

**Comandos de Moderación:**
• `/gban` - Banea globalmente a un usuario
• `/gmute` - Silencia globalmente a un usuario
• `/ungban` - Remueve ban global
• `/ungmute` - Remueve silencio global
• `/warn` - Advierte a un usuario
• `/kick` - Expulsa a un usuario
• `/ban` - Banea a un usuario del grupo

**Comandos de Información:**
• `/userinfo` - Muestra información detallada
• `/stats` - Estadísticas del grupo
• `/history` - Historial de acciones
• `/check` - Verifica estado de usuario
• `/whois` - Información detallada de usuario

**Comandos de Administración:**
• `/addadmin` - Añade un administrador
• `/deladmin` - Remueve un administrador
• `/admins` - Lista de administradores
• `/setlang` - Configura idioma
• `/settings` - Configuración del grupo

**Comandos de Button-box:**
• `/setmessage` - Configura mensaje
• `/setphoto` - Configura foto
• `/setgif` - Configura gif
• `/setvideo` - Configura video
• `/sethours` - Configura horas
• `/setbuttons` - Configura botones
• `/settimezone` - Configura zona horaria

**Comandos de Protección:**
• `/antispam` - Configura protección spam
• `/antiflood` - Configura anti-flood
• `/blacklist` - Palabras prohibidas
• `/whitelist` - Usuarios permitidos

**Formato de Uso:**
• Responde a un mensaje o usa @username/ID
• Para razones: /comando @usuario razón
• Para duración: /comando @usuario tiempo razón

**Niveles de Permisos:**
• Owner: Control total
• Admin: Moderación completa
• Mod: Comandos básicos
• User: Comandos informativos

Para más detalles sobre un comando usa:
/help comando
        """
        await event.respond(help_message)
    except Exception as e:
        logger.error(f"Error en comando help: {e}")

# Comandos de información
@client.on(events.NewMessage(pattern=r'[\.!/]userinfo(\s+|$)'))
@SecurityCheck.require_admin()
async def userinfo_cmd(event):
    """Comando para obtener información detallada de un usuario"""
    try:
        user = await get_target_user(event)
        if not user:
            await event.respond("❌ Usuario no encontrado.")
            return

        user_info = await UserManager.get_full_user_info(user.id)
        if not user_info:
            await event.respond("❌ Error obteniendo información del usuario.")
            return

        # Verificar estado de moderación
        db.cursor.execute('SELECT * FROM banned_users WHERE user_id = ?', (user.id,))
        ban_info = db.cursor.fetchone()
        
        db.cursor.execute('SELECT * FROM muted_users WHERE user_id = ?', (user.id,))
        mute_info = db.cursor.fetchone()

        # Obtener historial de acciones
        db.cursor.execute('''
            SELECT action_type, action_date, reason 
            FROM user_actions 
            WHERE user_id = ? 
            ORDER BY action_date DESC 
            LIMIT 5
        ''', (user.id,))
        recent_actions = db.cursor.fetchall()

        info_message = f"""
📊 **INFORMACIÓN DETALLADA DEL USUARIO** 📊

👤 **Datos Básicos:**
• ID: `{user.id}`
• Username: {user.username or "No disponible"}
• Nombre: {user.first_name or "No disponible"}
• Apellido: {user.last_name or "No disponible"}
• Bot: {"Sí" if user.bot else "No"}
• Verificado: {"Sí" if user.verified else "No"}
• Restringido: {"Sí" if user.restricted else "No"}
• Scam: {"Sí" if user.scam else "No"}

📈 **Estadísticas:**
• Mensajes totales: {user_info['message_count']}
• Advertencias: {user_info['warn_count']}
• Primera vez visto: {user_info['first_seen']}
• Última vez visto: {user_info['last_seen']}

🚫 **Estado de Moderación:**
• Baneado: {"Sí" if ban_info else "No"}
• Silenciado: {"Sí" if mute_info else "No"}

📝 **Notas:**
{user_info['notes'] or "Sin notas"}

🔄 **Acciones Recientes:**"""

        for action in recent_actions:
            info_message += f"\n• {action[0]} - {action[1]} - {action[2] or 'Sin razón'}"

        await event.respond(info_message)

    except Exception as e:
        logger.error(f"Error en userinfo: {e}")
        await event.respond("❌ Error al obtener información del usuario.")

# Ejecutar el cliente
if __name__ == '__main__':
    client.start(phone=PHONE)
    client.run_until_disconnected()
