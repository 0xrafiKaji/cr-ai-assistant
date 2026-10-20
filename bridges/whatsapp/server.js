const express = require('express');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcodeTerminal = require('qrcode-terminal');
const QRCode = require('qrcode');
const axios = require('axios');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: path.join(__dirname, '../../.env') });

const app = express();
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

const PORT = process.env.WHATSAPP_PORT || 3001;
const HOST = process.env.WHATSAPP_HOST || '127.0.0.1';
const PYTHON_BACKEND_URL = process.env.PYTHON_BACKEND_URL || 'http://localhost:8000';
const ADMIN_NAME = process.env.ADMIN_NAME || 'CR';
const ADMIN_PHONE = (process.env.ADMIN_PHONE || '').replace(/[^0-9]/g, '');
const SECRET_KEY = process.env.SECRET_KEY || 'cr_ai_assistant_default_secret_key_change_me';

// Security Middleware: Protect bridge REST endpoints from unauthorized external access
app.use((req, res, next) => {
    if (req.path === '/qr' || req.path === '/relink') return next();
    
    const clientIp = req.socket.remoteAddress;
    const isLocal = clientIp === '127.0.0.1' || clientIp === '::1' || clientIp === '::ffff:127.0.0.1';
    const token = req.headers['x-bridge-token'];
    
    if (!isLocal && token !== SECRET_KEY) {
        console.warn(`🚨 SECURITY BLOCKED: Unauthorized external request to ${req.path} from ${clientIp}`);
        return res.status(403).json({ error: 'Forbidden: Invalid or missing bridge authentication token' });
    }
    next();
});

let sock = null;
let isConnected = false;
let latestQR = null;
let isAutoReplyEnabled = true;
let reconnectTimer = null;
const lastAdminActivity = {}; // remoteJid -> timestamp
const lastFallbackPerSender = {}; // remoteJid -> timestamp
const pendingDMTimers = {}; // remoteJid -> { timer, messages: [], pushName, startTime }
const DM_DELAY_MS = 5 * 60 * 1000; // 5 minutes inactivity wait for personal DMs

const BOT_CONFIG_PATH = path.join(__dirname, '../../data/bot_config.json');

function loadBotConfig() {
    try {
        if (fs.existsSync(BOT_CONFIG_PATH)) {
            const raw = fs.readFileSync(BOT_CONFIG_PATH, 'utf-8');
            const data = JSON.parse(raw);
            if (typeof data.auto_reply_enabled === 'boolean') {
                isAutoReplyEnabled = data.auto_reply_enabled;
                console.log(`🤖 Loaded persistent auto-reply state: ${isAutoReplyEnabled ? 'ENABLED' : 'DISABLED'}`);
                return;
            }
        }
    } catch (e) {
        console.warn('⚠️ Could not read bot_config.json, using default true:', e.message);
    }
    isAutoReplyEnabled = true;
    saveBotConfig();
}

function saveBotConfig() {
    try {
        const dir = path.dirname(BOT_CONFIG_PATH);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(BOT_CONFIG_PATH, JSON.stringify({
            auto_reply_enabled: isAutoReplyEnabled,
            updated_at: new Date().toISOString()
        }, null, 2), 'utf-8');
    } catch (e) {
        console.error('⚠️ Could not save bot_config.json:', e.message);
    }
}

function getDelayedReply(type, text) {
    const hasBangla = /[\u0980-\u09FF]/.test(text || '');
    const isEnglish = /\b(what|when|where|is|are|will|can|please|there|you|hello|hi)\b/i.test(text || '') && !/\b(ki|kalke|ajke|ache|hobe|cr|tui|tumi|apni|bhai)\b/i.test(text || '');

    if (type === 'personal_plan') {
        if (hasBangla) {
            return `${ADMIN_NAME} এখন এভেইলেবল নেই, আমি ${ADMIN_NAME}-এর এআই এজেন্ট। ${ADMIN_NAME} এসে আপনাকে এই বিষয়ে জানাবে।`;
        } else if (isEnglish) {
            return `${ADMIN_NAME} is currently unavailable, I am ${ADMIN_NAME}'s AI agent. ${ADMIN_NAME} will check and let you know about this soon.`;
        } else {
            return `${ADMIN_NAME} ekhon available nai, ami ${ADMIN_NAME}-r AI agent. ${ADMIN_NAME} eshe apnake ei bishoye janabe.`;
        }
    } else { // 'availability'
        if (hasBangla) {
            return `${ADMIN_NAME} এখন এভেইলেবল নেই, আমি ${ADMIN_NAME}-এর এআই এজেন্ট। কীভাবে সাহায্য করতে পারি?`;
        } else if (isEnglish) {
            return `${ADMIN_NAME} is currently unavailable, I am ${ADMIN_NAME}'s AI agent. How can I help you?`;
        } else {
            return `${ADMIN_NAME} ekhon available nai, ami ${ADMIN_NAME}'r AI agent. Kivabe help korte pari?`;
        }
    }
}

function scheduleDelayedDMReply(sender, pushName, text, type) {
    const HUMAN_COOLDOWN_MS = 10 * 60 * 1000;
    if (pendingDMTimers[sender]) {
        pendingDMTimers[sender].messages.push(text);
        pendingDMTimers[sender].lastText = text;
        console.log(`📩 Additional unreplied DM from ${pushName} (${sender}): "${text}". (5-min timer already active)`);
        return;
    }

    console.log(`⏳ Scheduling 5-minute delayed auto-reply (${type}) for ${pushName} (${sender}): "${text}"...`);
    const timer = setTimeout(async () => {
        try {
            const pending = pendingDMTimers[sender];
            delete pendingDMTimers[sender];
            if (!pending) return;

            // Check if Rafi replied or was active in this chat in the last 10 minutes
            const lastActive = lastAdminActivity[sender] || 0;
            if (Date.now() - lastActive < HUMAN_COOLDOWN_MS) {
                console.log(`👤 Rafi was active with ${sender} within last 10 mins. Suppressing delayed assistant reply.`);
                return;
            }

            if (!sock || !isConnected) {
                console.warn(`⚠️ Cannot send delayed reply to ${sender}: WhatsApp not connected.`);
                return;
            }

            const replyText = getDelayedReply(pending.type, pending.lastText);
            console.log(`🤖 5 minutes elapsed without Rafi replying to ${sender}. Sending auto-reply (${pending.type}): "${replyText}"`);

            const sent = await sock.sendMessage(sender, { text: replyText });
            storeMessage(sent);
        } catch (err) {
            console.error(`Error in 5-min auto-reply dispatch to ${sender}:`, err.message);
        }
    }, DM_DELAY_MS);

    pendingDMTimers[sender] = {
        timer,
        type,
        messages: [text],
        lastText: text,
        pushName,
        timestamp: Date.now()
    };
}


// Message Store for Baileys retries & ratchet sync
const messageStore = new Map();
function storeMessage(msg) {
    if (msg?.key?.id && msg?.message) {
        messageStore.set(msg.key.id, msg.message);
        if (messageStore.size > 2000) {
            const first = messageStore.keys().next().value;
            messageStore.delete(first);
        }
    }
}

function cleanAuthFolder() {
    const authFolder = path.join(__dirname, 'auth_info_baileys');
    try {
        if (fs.existsSync(authFolder)) {
            fs.rmSync(authFolder, { recursive: true, force: true });
            fs.mkdirSync(authFolder, { recursive: true });
            console.log('🧹 Cleaned WhatsApp auth_info_baileys credentials.');
        }
    } catch (e) {
        console.error('Error cleaning auth folder:', e.message);
    }
}

function verifySessionIntegrity() {
    const authFolder = path.join(__dirname, 'auth_info_baileys');
    const credsPath = path.join(authFolder, 'creds.json');
    if (!fs.existsSync(credsPath)) return true;
    try {
        const creds = JSON.parse(fs.readFileSync(credsPath, 'utf-8'));
        const regId = creds.registrationId;
        const files = fs.readdirSync(authFolder);
        const sessionFiles = files.filter(f => f.startsWith('session-'));
        if (sessionFiles.length > 0 && regId) {
            const sample = JSON.parse(fs.readFileSync(path.join(authFolder, sessionFiles[0]), 'utf-8'));
            const sessRegId = Object.values(sample._sessions || {})[0]?.registrationId;
            if (sessRegId && sessRegId !== regId) {
                console.error(`🚨 [Session Conflict] Creds registrationId (${regId}) does not match old session files (${sessRegId})! Pruning stale session files.`);
                sessionFiles.forEach(f => {
                    try { fs.unlinkSync(path.join(authFolder, f)); } catch (e) {}
                });
            }
        }
    } catch (e) {
        console.warn('⚠️ Could not verify session integrity:', e.message);
    }
    return true;
}

// Endpoint to toggle auto-reply from Dashboard
app.post('/api/bot-toggle', (req, res) => {
    if (typeof req.body.enabled === 'boolean') {
        isAutoReplyEnabled = req.body.enabled;
    } else {
        isAutoReplyEnabled = !isAutoReplyEnabled;
    }
    saveBotConfig();
    console.log(`🤖 Auto-reply is now: ${isAutoReplyEnabled ? 'ENABLED' : 'DISABLED'} (Saved to disk)`);
    res.json({ auto_reply_enabled: isAutoReplyEnabled });
});

app.get('/api/bot-toggle', (req, res) => {
    res.json({ auto_reply_enabled: isAutoReplyEnabled });
});

async function safeStartWhatsApp() {
    try {
        await startWhatsApp();
    } catch (err) {
        console.error('⚠️ WhatsApp connection attempt failed (likely network offline):', err.message);
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => {
            console.log('🔄 Retrying WhatsApp connection after error...');
            safeStartWhatsApp();
        }, 5000);
    }
}

async function startWhatsApp() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    if (sock) {
        try {
            sock.ev.removeAllListeners();
            sock.end();
        } catch (e) {}
    }

    if (!verifySessionIntegrity()) {
        console.log('🧹 Automatically clearing corrupted WhatsApp credentials to prevent PreKey decryption errors...');
        cleanAuthFolder();
    }

    const authFolder = path.join(__dirname, 'auth_info_baileys');
    const { state, saveCreds } = await useMultiFileAuthState(authFolder);

    let version = [2, 3000, 1015901307];
    try {
        const v = await fetchLatestBaileysVersion();
        if (v && v.version) version = v.version;
    } catch (e) {
        console.warn('⚠️ Could not fetch latest Baileys version online (offline/laggy). Using fallback version.');
    }

    sock = makeWASocket({
        version,
        logger: pino({ level: 'warn' }),
        printQRInTerminal: false,
        auth: state,
        browser: ["CR AI Assistant", "Chrome", "120.0.0"],
        syncFullHistory: false,
        markOnlineOnConnect: true,
        getMessage: async (key) => {
            return messageStore.get(key.id);
        }
    });

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            latestQR = qr;
            console.log('\n======================================================');
            console.log('📲 SCAN THIS QR CODE WITH WHATSAPP ON ADMIN PHONE:');
            console.log('======================================================\n');
            qrcodeTerminal.generate(qr, { small: true });

            // Also write QR image to data/whatsapp_qr.png
            const qrPath = path.join(__dirname, '../../data/whatsapp_qr.png');
            QRCode.toFile(qrPath, qr, { width: 350, margin: 2 }).catch(e => console.error('Failed to write QR image:', e.message));
        }

        if (connection === 'close') {
            const err = lastDisconnect?.error;
            const statusCode = err?.output?.statusCode;
            const isStream515 = Boolean(
                err?.message?.includes('restart required') ||
                statusCode === 515 ||
                err?.node?.attrs?.code === '515' ||
                String(err).includes('515')
            );
            const isLoggedOut = statusCode === DisconnectReason.loggedOut;
            console.log('Connection closed. Reason:', err?.message || err, 'Logged out:', isLoggedOut, 'Restart515:', isStream515);
            isConnected = false;

            if (isLoggedOut) {
                console.log('🚪 Session logged out by WhatsApp. Cleaning credentials for new scan...');
                cleanAuthFolder();
                if (reconnectTimer) clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(() => {
                    startWhatsApp().catch(err => console.error('Restart after logout failed:', err.message));
                }, 2000);
            } else if (isStream515) {
                console.log('🔄 Handshake restart required (code 515). Reconnecting immediately to complete WhatsApp pairing...');
                if (reconnectTimer) clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(() => {
                    startWhatsApp().catch(err => console.error('515 Reconnect failed:', err.message));
                }, 1000);
            } else {
                if (reconnectTimer) clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(() => {
                    startWhatsApp().catch(err => {
                        console.error('Reconnect attempt failed:', err.message);
                    });
                }, 3000);
            }
        } else if (connection === 'open') {
            const hasUser = Boolean(sock?.user?.id || sock?.authState?.creds?.me?.id);
            if (hasUser) {
                console.log('✅ WhatsApp Bridge successfully connected and verified with WhatsApp servers! User:', sock?.user?.id || sock?.authState?.creds?.me?.id);
                isConnected = true;
                latestQR = null;
            } else {
                console.warn('⚠️ WhatsApp connected, but no user credentials found. Awaiting pairing...');
                isConnected = false;
            }
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // Handle Incoming & Outgoing Messages
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        console.log(`📩 [messages.upsert] Event received. Type: "${type}", Messages count: ${messages?.length || 0}`);
        if (type !== 'notify' && type !== 'append') return;
        for (const msg of messages) {
            if (!msg.message) continue;

            const nowSec = Math.floor(Date.now() / 1000);
            if (type === 'append' && msg.messageTimestamp && (nowSec - msg.messageTimestamp > 120)) {
                continue; // Skip stale historical sync
            }

            storeMessage(msg);

            const sender = msg.key.remoteJid;
            const isGroup = sender.endsWith('@g.us');
            const pushName = msg.pushName || 'Student';

            // 1. Extract text message content (unwrap ephemeral/viewOnce/template containers)
            const unwrapped = msg.message.ephemeralMessage?.message ||
                              msg.message.viewOnceMessage?.message ||
                              msg.message.viewOnceMessageV2?.message ||
                              msg.message.documentWithCaptionMessage?.message ||
                              msg.message;

            const text = unwrapped.conversation ||
                         unwrapped.extendedTextMessage?.text ||
                         unwrapped.imageMessage?.caption ||
                         unwrapped.videoMessage?.caption ||
                         unwrapped.documentMessage?.caption || '';

            console.log(`📩 [Msg Inspection] from: "${sender}" (${pushName}), fromMe: ${msg.key.fromMe}, text: "${text}"`);

            if (!text.trim()) continue;

            const trimmed = text.trim();
            const isCommand = trimmed.startsWith('!');

            // 2. SENDER IDENTITY & PERMISSION CHECK
            const senderCleanPhone = sender.split('@')[0].replace(/[^0-9]/g, '');
            const isFromMe = msg.key.fromMe === true;
            const isSelfChat = isFromMe || (ADMIN_PHONE.length > 5 && senderCleanPhone === ADMIN_PHONE);
            const isSenderAdmin = isFromMe || (ADMIN_PHONE.length > 5 && senderCleanPhone === ADMIN_PHONE);
            const HUMAN_COOLDOWN_MS = 10 * 60 * 1000; // 10 minutes active chat window

            // Direct Agent or Academic Query intent (STRICT WORD BOUNDARIES TO PREVENT FALSE POSITIVES)
            // e.g. "selection" must NOT match "ct", "coffee" must NOT match "fee", "middle" must NOT match "mid"
            const isAcademicQuery = /\b(routine|rutine|rotine|class|classes|klas|exam|exams|exm|xm|midterm|mid|ct|quiz|quizzes|assignment|assignments|holiday|holidays|chuti|schedule|calendar|admit|notice|fee|fees|tuition|attendance|attend|attandance|syllabus|result|results|algorithm|search|code|program)\b/i.test(trimmed) || /(রুটিন|ক্লাস|পরীক্ষা|ছুটি|এডমিট|ক্যালেন্ডার|সিলেবাস|উপস্থিতি|রেজাল্ট)/i.test(trimmed);
            const isDirectAgentCall = /^(agent|assistant|bot|\!)/i.test(trimmed) || /\b(agent|assistant|bot)\b\s*\?/i.test(trimmed);

            // Personal Human-to-Human Conversation detection:
            // Check if message is directed at RAFI the human using 2nd-person address/verbs ("tui", "jabi", "ashbi", "korbi", "koi tui", etc.)
            const isPersonalAddressToRafi = /\b(tui|tumi|apni|tor|tomar|apnar|jabi|ashbi|korbi|dibishi|korchos|gesos|dish|jash|ashos|koros|shun|shuno|bhai|bro|koi\s*tui|kothay\s*tui|dekha\s*korbi|call\s*de)\b/i.test(trimmed) || /(তুই|তুমি|আপনার|তোর|যাবি|আসবি|করবি|দিবি|শুন|কল\s*দে|কই\s*তুই)/i.test(trimmed);

            // Questions asking Rafi about his personal plans/actions (e.g. "rafi kalke university jabi?", "rafi ashbi?", "class korbi?")
            const isPersonalPlanQuery = (
                /\b(jabi|ashbi|korbi|jash|ashos|koros|jaben|ashben|korben|dekha\s*korbi|thakbi|jawa\s*hobe)\b/i.test(trimmed) ||
                /(যাবি|আসবি|করবি|যাবেন|আসবেন|থাকবি|দেখা\s*করবি)/i.test(trimmed)
            ) && (
                /\b(rafi|tui|tumi|apni|bro|bhai|re)\b/i.test(trimmed) ||
                /\b(university|varsity|versity|campus|class|klas|dept|lab|kalke|kal|ajke|aajke)\b/i.test(trimmed) ||
                /(তুই|তুমি|আপনার|রাফি|ভার্সিটি|ক্যাম্পাস|ক্লাস|কালকে|আজকে)/i.test(trimmed)
            );

            // Questions asking if Rafi is online / active / present ("ami achi naki", "rafi achis?", "kire achis?", "rafi koi?", "is rafi there?")
            const isAvailabilityQuery = (
                /\b(rafi\s*(achis|achos|achi|ache|asen|aso|available|active)|achis\s*re|kire\s*achis|achis\s*naki|kothay\s*tui|koi\s*tui|free\s*achis|active\s*achis|online\s*achis|where\s*is\s*rafi|is\s*rafi\s*there)\b/i.test(trimmed) ||
                /^(achis|achos|ache\s*naki|achis\s*naki|koi\s*re|kire)\b/i.test(trimmed) ||
                /(রাফি\s*(আছিস|আছো|আছে|আছেন|ফ্রি)|আছিস\s*রে|কই\s*তুই|কোথায়\s*তুই|ফ্রি\s*আছিস|আছিস\s*নাকি)/i.test(trimmed)
            );

            // 3. HUMAN CHAT ACTIVITY & SENDER SHIELD:
            // If Rafi sends a manual message to ANY human contact or group:
            // -> Mark Rafi active in this chat (10 minute cooldown)
            // -> Cancel any pending DM timers
            // -> NEVER process Rafi's outgoing messages to other people as bot queries!
            if (isFromMe) {
                if (!isSelfChat) {
                    lastAdminActivity[sender] = Date.now();
                    if (pendingDMTimers[sender]) {
                        clearTimeout(pendingDMTimers[sender].timer);
                        delete pendingDMTimers[sender];
                    }
                    console.log(`👤 Rafi is active in conversation (${sender}). Auto-reply suppressed.`);
                    continue; // STOP! Rafi is chatting with someone. Never reply to Rafi's own messages!
                }
            }

            // 3b. ACTIVE CONVERSATION GUARD:
            // If Rafi sent a message in this chat within the last 10 minutes,
            // Rafi is actively engaged in a human conversation! The bot MUST STAY COMPLETELY SILENT!
            const lastActive = lastAdminActivity[sender] || 0;
            const isConversationActiveWithRafi = (Date.now() - lastActive) < HUMAN_COOLDOWN_MS;
            if (isConversationActiveWithRafi && !isSelfChat && !isCommand) {
                console.log(`👤 Active conversation in (${sender}). Rafi spoke ${Math.round((Date.now() - lastActive) / 1000)}s ago. Assistant staying completely silent.`);
                continue;
            }

            // 4. COMMAND PERMISSION CHECK:
            // Public student commands (!routine, !cts, !help, !limit, etc.) are allowed for everyone.
            // Admin commands (!bot, !sync, !broadcast, !approve, etc.) are strictly for Rafi.
            const isPublicCmd = ['!routine', '!cts', '!assessments', '!help', '!menu', '!attendance', '!limit', '!usage', '!quota', '!ailimit'].some(c => trimmed.toLowerCase().startsWith(c));

            if (isCommand && !isSenderAdmin && !isPublicCmd) {
                console.warn(`🚨 SECURITY BLOCKED: Unauthorized user ${sender} (${pushName}) attempted command: "${trimmed}"`);
                await sock.sendMessage(sender, {
                    text: `⛔ *Access Denied!*\nOnly ${ADMIN_NAME} is authorized to execute assistant admin commands.`
                });
                continue;
            }

            // 5. DIRECT BOT TOGGLE & COOLDOWN RESET COMMANDS (Only executable by verified admin!)
            if (isCommand && isSenderAdmin) {
                const cmdLower = trimmed.toLowerCase();
                if (cmdLower === '!bot on') {
                    isAutoReplyEnabled = true;
                    saveBotConfig();
                    console.log('🤖 Auto-reply ENABLED via WhatsApp admin command (Saved to disk)');
                    await sock.sendMessage(sender, { text: `🤖 *Auto-Reply Enabled!*\nAgent will now answer student queries when ${ADMIN_NAME} is away.` });
                    continue;
                }
                if (cmdLower === '!bot off') {
                    isAutoReplyEnabled = false;
                    saveBotConfig();
                    console.log('⏸️ Auto-reply DISABLED via WhatsApp admin command (Saved to disk)');
                    await sock.sendMessage(sender, { text: `⏸️ *Auto-Reply Disabled!*\nAgent is paused. ${ADMIN_NAME} can chat freely without bot replies.` });
                    continue;
                }
                if (cmdLower === '!reset' || cmdLower === '!cooldown 0' || cmdLower === '!cooldown off') {
                    for (const k in lastAdminActivity) delete lastAdminActivity[k];
                    for (const k in lastFallbackPerSender) delete lastFallbackPerSender[k];
                    for (const k in pendingDMTimers) {
                        clearTimeout(pendingDMTimers[k].timer);
                        delete pendingDMTimers[k];
                    }
                    console.log('🔄 All chat cooldowns, pending timers, and fallback timers reset!');
                    await sock.sendMessage(sender, { text: "🔄 *Cooldowns Reset!*\nAll chat cooldowns and fallback timers have been cleared. Bot will reply immediately." });
                    continue;
                }
            }

            // 6. CHECK IF BOT IS DISABLED GLOBALLY
            if (!isAutoReplyEnabled && !isCommand) {
                console.log(`⏸️ Auto-reply is currently DISABLED. Skipping message from ${pushName}`);
                continue;
            }

            // 7. GROUP CHATTER FILTER:
            // In WhatsApp groups:
            // 1. MUST be a bot command starting with "!"
            // 2. OR someone explicitly summons the bot/agent (e.g. "agent ...", "bot ...", "@bot")
            // NEVER trigger in a group just because someone casually mentioned "rafi"! (They are talking to classmate Rafi!)
            const isExplicitlySummonedInGroup = isGroup && (
                isDirectAgentCall ||
                (ADMIN_PHONE.length > 5 && msg.message.extendedTextMessage?.contextInfo?.mentionedJid?.some(j => j.includes(ADMIN_PHONE)))
            );

            if (isGroup && !isCommand && !isExplicitlySummonedInGroup) {
                continue;
            }

            // 8. PERSONAL 1-ON-1 CHAT (DM):
            // In private 1-on-1 chats:
            // - If someone asks Rafi about his personal plans ("rafi kalke university jabi?"):
            //   Do NOT answer immediately with routine/class info! Schedule 5-minute delayed auto-reply.
            // - If someone asks if Rafi is online / active ("ami achi naki", "rafi achis?"):
            //   Schedule 5-minute delayed auto-reply ("Rafi ekhon available nai, ami Rafi'r AI agent. Kivabe help korte pari?")
            // - If it's a command (!routine, !limit) or direct agent inquiry ("agent ..."):
            //   Answer immediately!
            // - If it's an objective academic query ("routine ta de", "kalke make up class ache?", "ct ache?"):
            //   Answer immediately!
            if (!isGroup && !isSelfChat) {
                if (isPersonalPlanQuery && !isCommand && !isDirectAgentCall) {
                    scheduleDelayedDMReply(sender, pushName, trimmed, 'personal_plan');
                    continue;
                }

                if (isAvailabilityQuery && !isCommand && !isDirectAgentCall) {
                    scheduleDelayedDMReply(sender, pushName, trimmed, 'availability');
                    continue;
                }

                if (isPersonalAddressToRafi && !isAcademicQuery && !isCommand && !isDirectAgentCall) {
                    console.log(`💬 Personal message directed to Rafi from ${pushName} (${sender}): "${trimmed}". Assistant staying silent.`);
                    continue;
                }

                if (!isCommand && !isDirectAgentCall && !isAcademicQuery) {
                    console.log(`💬 Casual/non-academic DM from ${pushName} (${sender}): "${trimmed}". Assistant staying silent.`);
                    continue;
                }
            }

            // 9. IMMEDIATE DISPATCH FOR ACADEMIC QUERIES, COMMANDS, AGENT INQUIRIES & GROUP QUERIES
            console.log(`📩 Immediate dispatch from ${pushName} (${sender}): "${trimmed}"`);

            try {
                const response = await axios.post(`${PYTHON_BACKEND_URL}/api/whatsapp/incoming`, {
                    sender_id: sender,
                    sender_name: isSenderAdmin ? `Admin ${ADMIN_NAME}` : pushName,
                    message: trimmed,
                    is_group: isGroup,
                    is_admin: isSenderAdmin
                }, {
                    headers: {
                        'X-Bridge-Token': SECRET_KEY
                    }
                });

                const reply = response.data?.reply;
                const isFallback = response.data?.is_fallback || false;

                // GROUP CHAT SAFETY RULE:
                // Never send fallback messages into WhatsApp groups during normal member talk.
                // Only reply in groups if the bot has an affirmative answer or explicit command (!).
                if (isGroup && isFallback && !isCommand) {
                    console.log(`🤐 [Group Safety] Query in group (${sender}) resulted in unknown info. Staying silent.`);
                    continue;
                }

                if (reply) {
                    await new Promise(r => setTimeout(r, 1000));
                    const sent = await sock.sendMessage(sender, { text: reply });
                    storeMessage(sent);
                    console.log(`📤 Sent reply to ${sender}`);
                }
            } catch (err) {
                console.error('Error forwarding message to Python backend:', err.message);
            }
        }
    });
}

// REST API for Python backend to send outgoing messages/broadcasts
app.post('/api/send-message', async (req, res) => {
    const { to, message, image_base64, image_path } = req.body;
    if (!to || (!message && !image_base64 && !image_path)) {
        return res.status(400).json({ error: 'Missing "to" or content' });
    }

    if (!sock || !isConnected) {
        console.warn(`⚠️ Warning: WhatsApp not connected. Simulated message to ${to}:\n${message}`);
        return res.json({ status: 'simulated', warning: 'WhatsApp not currently connected' });
    }

    let targetJid = to;
    if (to.includes('chat.whatsapp.com/')) {
        const code = to.split('chat.whatsapp.com/')[1].split('/')[0].split('?')[0].trim();
        try {
            const groupInfo = await sock.groupGetInviteInfo(code);
            if (groupInfo && groupInfo.id) {
                targetJid = groupInfo.id;
                console.log(`🎯 Resolved WhatsApp Invite Link to Group JID: ${targetJid}`);
            }
        } catch (e) {
            console.warn(`⚠️ Could not resolve group invite link: ${e.message}`);
        }
    }

    try {
        let sentMsg = null;
        if (image_base64) {
            const buffer = Buffer.from(image_base64, 'base64');
            sentMsg = await sock.sendMessage(targetJid, { image: buffer, caption: message || '' });
            console.log(`📢 Broadcasted image notice with caption to ${targetJid}`);
        } else if (image_path) {
            sentMsg = await sock.sendMessage(targetJid, { image: { url: image_path }, caption: message || '' });
            console.log(`📢 Broadcasted image notice from path with caption to ${targetJid}`);
        } else {
            sentMsg = await sock.sendMessage(targetJid, { text: message });
            console.log(`📢 Broadcasted / sent text message to ${targetJid}`);
        }
        if (sentMsg) storeMessage(sentMsg);
        return res.json({ status: 'success', target_jid: targetJid });
    } catch (err) {
        console.error('Failed to send WhatsApp message:', err.message);
        return res.status(500).json({ error: err.message });
    }
});

// Re-link & Session Reset Endpoint
async function handleRelink(req, res) {
    try {
        console.log('🔄 Triggering full WhatsApp session re-link & QR regeneration...');
        isConnected = false;
        latestQR = null;
        if (sock) {
            try {
                sock.ev.removeAllListeners();
                sock.end();
            } catch (e) {}
        }
        cleanAuthFolder();
        if (reconnectTimer) clearTimeout(reconnectTimer);
        setTimeout(() => {
            startWhatsApp().catch(err => console.error('Relink start failed:', err));
        }, 1200);

        if (req.accepts('html')) {
            return res.send(`
                <html>
                <head>
                    <title>Resetting WhatsApp...</title>
                    <meta http-equiv="refresh" content="3;url=/qr">
                </head>
                <body style="display:flex;align-items:center;justify-content:center;height:100vh;background:#0f172a;color:white;font-family:sans-serif;text-align:center;">
                    <div style="background:#1e293b;padding:36px;border-radius:16px;border:1px solid #334155;max-width:400px;">
                        <div style="font-size:40px;margin-bottom:12px;">🔄</div>
                        <h2 style="color:#38bdf8;margin:0 0 8px 0;">Resetting WhatsApp Session...</h2>
                        <p style="color:#94a3b8;font-size:14px;margin-bottom:20px;">Old session keys cleared. Generating a fresh QR code now...</p>
                        <a href="/qr" style="display:inline-block;padding:10px 20px;background:#2563eb;color:white;text-decoration:none;border-radius:8px;font-weight:600;font-size:13px;">View QR Code</a>
                    </div>
                </body>
                </html>
            `);
        }
        return res.json({ status: 'success', message: 'WhatsApp session reset. Generating fresh QR.' });
    } catch (err) {
        return res.status(500).json({ error: err.message });
    }
}

app.get('/relink', handleRelink);
app.post('/api/relink', handleRelink);
app.post('/api/reset-session', handleRelink);

app.get('/qr', async (req, res) => {
    const hasUser = Boolean(sock?.user?.id || sock?.authState?.creds?.me?.id);
    if (isConnected && hasUser) {
        const userName = sock?.user?.name || ADMIN_NAME;
        const userPhone = (sock?.user?.id || '').split('@')[0].split(':')[0] || ADMIN_PHONE;
        return res.send(`
            <html>
            <head>
                <title>WhatsApp Connected - CR's AI Assistant</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;background:#0f172a;color:white;text-align:center;margin:0;padding:20px;">
                <div style="background:#1e293b;padding:40px;border-radius:20px;border:1px solid #334155;max-width:420px;box-shadow:0 15px 35px rgba(0,0,0,0.4);">
                    <div style="font-size:52px;margin-bottom:8px;">✅</div>
                    <h1 style="color:#10b981;margin:10px 0;font-size:22px;">WhatsApp is Connected!</h1>
                    <p style="color:#e2e8f0;font-size:15px;margin:8px 0;font-weight:600;">Linked Account: ${userName} (${userPhone})</p>
                    <p style="color:#94a3b8;font-size:13px;margin-bottom:24px;">Your AI Assistant is actively listening for student queries and routine questions.</p>
                    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
                        <a href="http://localhost:8000" style="padding:10px 22px;background:#2563eb;color:white;text-decoration:none;border-radius:10px;font-weight:bold;font-size:13px;">Dashboard</a>
                        <a href="/relink" onclick="return confirm('Disconnect and generate a new QR code?')" style="padding:10px 18px;background:#e11d48;color:white;text-decoration:none;border-radius:10px;font-weight:bold;font-size:13px;">🔄 Re-link / Scan New QR</a>
                    </div>
                </div>
            </body>
            </html>
        `);
    }

    if (!latestQR) {
        return res.send(`
            <html>
            <head>
                <title>Generating QR - CR's AI Assistant</title>
                <meta http-equiv="refresh" content="3">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;background:#0f172a;color:white;text-align:center;margin:0;padding:20px;">
                <div style="background:#1e293b;padding:40px;border-radius:20px;border:1px solid #334155;max-width:400px;">
                    <div style="font-size:48px;margin-bottom:12px;">⏳</div>
                    <h2 style="color:#38bdf8;margin:0 0 10px 0;font-size:20px;">Generating WhatsApp QR Code...</h2>
                    <p style="color:#94a3b8;font-size:13px;">Initializing fresh secure connection. This page auto-refreshes every 3 seconds.</p>
                    <div style="margin-top:20px;">
                        <a href="/relink" style="color:#f43f5e;font-size:12px;text-decoration:underline;">Force Reset Auth Keys</a>
                    </div>
                </div>
            </body>
            </html>
        `);
    }

    let qrDataUrl = '';
    try {
        qrDataUrl = await QRCode.toDataURL(latestQR, { width: 280, margin: 2 });
    } catch (e) {
        qrDataUrl = `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(latestQR)}`;
    }

    res.send(`
        <html>
        <head>
            <title>Scan WhatsApp QR - CR's AI Assistant</title>
            <meta http-equiv="refresh" content="12">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;background:#0f172a;color:white;margin:0;padding:20px;">
            <div style="background:#1e293b;padding:32px;border-radius:20px;box-shadow:0 15px 35px rgba(0,0,0,0.5);text-align:center;max-width:390px;border:1px solid #334155;">
                <h2 style="margin-top:0;color:#38bdf8;font-size:20px;margin-bottom:6px;">📲 Scan with WhatsApp</h2>
                <p style="color:#94a3b8;font-size:13px;margin-bottom:16px;">Open WhatsApp on phone ➔ Linked Devices ➔ <b>Link a Device</b></p>
                <div style="background:white;padding:14px;border-radius:14px;display:inline-block;box-shadow:0 8px 20px rgba(0,0,0,0.3);">
                    <img src="${qrDataUrl}" width="260" height="260" alt="WhatsApp QR Code" style="display:block;" />
                </div>
                <p style="color:#64748b;font-size:11px;margin-top:14px;margin-bottom:16px;">Auto-refreshes every 12s to keep the QR code fresh.</p>
                <div style="display:flex;gap:8px;justify-content:center;">
                    <a href="/relink" style="padding:8px 16px;background:#334155;color:#e2e8f0;text-decoration:none;border-radius:8px;font-size:12px;font-weight:600;">🔄 Regenerate QR</a>
                </div>
            </div>
        </body>
        </html>
    `);
});

app.get('/api/qr', (req, res) => {
    res.json({ connected: isConnected, qr: latestQR });
});

app.get('/api/status', (req, res) => {
    const hasUser = Boolean(sock?.user?.id || sock?.authState?.creds?.me?.id);
    res.json({
        connected: isConnected && hasUser,
        user: sock?.user,
        auto_reply_enabled: isAutoReplyEnabled
    });
});

app.get('/api/debug-status', async (req, res) => {
    try {
        let groups = [];
        if (sock && isConnected) {
            const grpMap = await sock.groupFetchAllParticipating().catch(err => {
                return { error: err.message };
            });
            groups = Object.keys(grpMap || {});
        }
        res.json({
            connected: isConnected,
            user: sock?.user,
            groups_count: groups.length,
            groups: groups.slice(0, 10),
            pending_dm_timers: Object.keys(pendingDMTimers),
            auto_reply_enabled: isAutoReplyEnabled
        });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(PORT, () => {
    loadBotConfig();
    console.log(`🚀 WhatsApp Bridge Microservice running on http://localhost:${PORT}`);
    safeStartWhatsApp();
});
