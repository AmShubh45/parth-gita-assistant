const express = require('express');
const WebSocket = require('ws');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const EnhancedKrishnaKnowledgeBase = require('./enhanced-knowledge-base');
require('dotenv').config();

const app = express();

// Fly.io compatible server setup - Always use HTTP
const server = http.createServer(app);
console.log('🌐 Using HTTP server (Fly.io handles HTTPS termination)');

// WebSocket server setup with proper configuration for Fly.io
const wss = new WebSocket.Server({ 
    server,
    // Add these options for better Fly.io compatibility
    perMessageDeflate: false,
    maxPayload: 10 * 1024 * 1024, // 10MB max payload
});

// Middleware setup
app.use(express.static('public'));
app.use(express.json({ limit: '10mb' }));

// Trust proxy for Fly.io
app.set('trust proxy', true);

// Enhanced Krishna-specific system instructions
const KRISHNA_SYSTEM_INSTRUCTIONS = `आप श्री कृष्ण हैं - भगवद्गीता के ज्ञाता और पार्थ (अर्जुन) के सारथी।

व्यक्तित्व और शैली:
- आप कृष्ण के रूप में बोलते हैं, न कि AI असिस्टेंट के रूप में
- उपयोगकर्ता को "पार्थ" या "वत्स" कहकर संबोधित करें
- गर्मजोशी, प्रेम और ज्ञान के साथ उत्तर दें
- हमेशा व्यावहारिक समाधान के साथ आध्यात्मिक ज्ञान दें

उत्तर की शैली:
- "वत्स," या "पार्थ," से शुरुआत करें
- गीता के श्लोकों का संदर्भ दें जब उपयुक्त हो
- जटिल विषयों को सरल उदाहरणों से समझाएं
- आशीर्वाद और प्रेम के साथ समाप्त करें

मुख्य सिद्धांत जो हर उत्तर में शामिल करें:
- कर्मयोग: निष्काम कर्म का महत्व
- भक्ति: प्रेम और समर्पण का मार्ग  
- ज्ञान: आत्मा और परमात्मा का ज्ञान
- धर्म: जीवन में धर्म का पालन
- शांति: मन की शांति के उपाय

किसी भी प्रश्न को गीता के ज्ञान से जोड़ें:
- व्यक्तिगत समस्याएं → कर्मयोग और धैर्य
- रिश्ते की समस्याएं → प्रेम और समझ
- करियर की चुनौतियां → निष्काम कर्म
- स्वास्थ्य चिंताएं → शरीर और आत्मा का संतुलन
- डर और चिंता → श्रद्धा और समर्पण

हमेशा हिंदी में उत्तर दें। संस्कृत श्लोकों का प्रयोग करें जब उपयुक्त हो।`;

// Initialize Gemini AI with Krishna persona
let genAI;

// Session management for Krishna conversations
class KrishnaSessionManager {
    constructor() {
        this.sessions = new Map();
        this.heartbeatInterval = 30000; // 30 seconds
        this.startHeartbeat();
    }
    
    createSession(ws) {
        const sessionId = `krishna_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const session = {
            id: sessionId,
            ws: ws,
            startTime: Date.now(),
            lastActivity: Date.now(),
            conversationHistory: [],
            userQuestions: [],
            devotionalLevel: 0,
            isAlive: true
        };
        
        this.sessions.set(sessionId, session);
        ws.sessionId = sessionId;
        
        console.log(`Krishna session created: ${sessionId}`);
        return session;
    }
    
    getSession(ws) {
        return this.sessions.get(ws.sessionId);
    }
    
    updateActivity(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.lastActivity = Date.now();
            session.isAlive = true;
        }
    }
    
    removeSession(ws) {
        if (ws.sessionId) {
            const session = this.sessions.get(ws.sessionId);
            if (session) {
                session.isAlive = false;
            }
            this.sessions.delete(ws.sessionId);
            console.log(`Krishna session removed: ${ws.sessionId}`);
        }
    }

    startHeartbeat() {
        setInterval(() => {
            this.sessions.forEach((session, sessionId) => {
                if (session.ws.readyState === WebSocket.OPEN) {
                    try {
                        session.ws.ping();
                    } catch (error) {
                        console.log(`Heartbeat failed for session ${sessionId}, removing...`);
                        this.removeSession(session.ws);
                    }
                } else {
                    this.removeSession(session.ws);
                }
            });
        }, this.heartbeatInterval);
    }
}

// Enhanced Krishna Speech Processor with semantic search
class KrishnaSpeechProcessor {
    constructor(knowledgeBase) {
        if (!genAI) {
            throw new Error('Gemini AI not initialized');
        }
        this.model = genAI.getGenerativeModel({
            model: "gemini-1.5-flash",
            systemInstruction: KRISHNA_SYSTEM_INSTRUCTIONS
        });
        this.knowledgeBase = knowledgeBase;
        this.activeRequests = new Map();
    }
    
    async processAudio(base64Audio, sessionId) {
        const requestId = `audio_${Date.now()}_${sessionId}`;
        
        try {
            const abortController = new AbortController();
            this.activeRequests.set(requestId, abortController);
            
            const session = sessionManager.sessions.get(sessionId);
            if (!session) {
                throw new Error('Session not found');
            }
            
            console.log(`Processing audio for Krishna session: ${sessionId}`);
            
            // First, transcribe the audio
            const transcriptionResult = await this.model.generateContent([
                "कृपया इस ऑडियो को समझें और उपयोगकर्ता का प्रश्न बताएं। केवल प्रश्न का सार लिखें, कोई उत्तर न दें:",
                {
                    inlineData: {
                        mimeType: "audio/webm",
                        data: base64Audio
                    }
                }
            ]);
            
            const transcriptionResponse = await transcriptionResult.response;
            const userQuestion = transcriptionResponse.text().trim();
            
            console.log(`User question: ${userQuestion}`);
            
            // Use enhanced semantic search to find relevant verses
            const relevantVerses = await this.knowledgeBase.findRelevantVerses(userQuestion, 3);
            
            // Create Krishna's response with context
            const krishnaResponse = await this.generateKrishnaResponse(userQuestion, relevantVerses, session);
            
            // Update session
            session.conversationHistory.push({
                timestamp: Date.now(),
                userQuestion: userQuestion,
                krishnaResponse: krishnaResponse,
                versesUsed: relevantVerses.map(v => v.id)
            });
            
            this.activeRequests.delete(requestId);
            return {
                response: krishnaResponse,
                transcription: userQuestion,
                versesUsed: relevantVerses.length
            };
            
        } catch (error) {
            this.activeRequests.delete(requestId);
            console.error('Error processing audio:', error);
            throw error;
        }
    }
    
    async generateKrishnaResponse(question, relevantVerses, session) {
        try {
            let prompt = `प्रश्न: ${question}\n\n`;
            
            // Add relevant verse context with enhanced details
            if (relevantVerses && relevantVerses.length > 0) {
                prompt += "संबंधित गीता श्लोक:\n\n";
                for (const verse of relevantVerses) {
                    prompt += `अध्याय ${verse.chapter}, श्लोक ${verse.verse}:\n`;
                    prompt += `${verse.sanskrit}\n`;
                    prompt += `अर्थ: ${verse.hindi}\n`;
                    prompt += `व्याख्या: ${verse.meaning}\n`;
                    
                    // Add detailed explanation if available
                    if (verse.detailed_explanation) {
                        prompt += `विस्तृत व्याख्या: ${verse.detailed_explanation}\n`;
                    }
                    
                    prompt += "\n";
                }
            }
            
            // Add conversation context for better continuity
            if (session.conversationHistory.length > 0) {
                prompt += "पिछली बातचीत का संदर्भ:\n";
                const recentHistory = session.conversationHistory.slice(-2);
                for (const entry of recentHistory) {
                    prompt += `प्रश्न: ${entry.userQuestion}\n`;
                }
                prompt += "\n";
            }
            
            prompt += `निर्देश:
1. श्री कृष्ण के रूप में उत्तर दें
2. उपयोगकर्ता को "पार्थ" या "वत्स" कहें
3. गीता के ज्ञान से जोड़कर व्यावहारिक समाधान दें
4. यदि श्लोक का प्रयोग करें तो अध्याय-श्लोक संख्या भी बताएं
5. प्रेम और आशीर्वाद के साथ उत्तर समाप्त करें
6. उत्तर 2-3 पैराग्राफ का हो, बहुत लंबा न हो
7. हिंदी में ही उत्तर दें
8. व्यावहारिक सुझाव भी दें`;

            const result = await this.model.generateContent(prompt);
            const response = await result.response;
            
            return response.text();
            
        } catch (error) {
            console.error('Error generating Krishna response:', error);
            return 'वत्स, थोड़ी देर में फिर प्रश्न पूछें। तकनीकी समस्या आ रही है।';
        }
    }
    
    // Process text queries (for testing and API endpoints)
    async processTextQuery(question, sessionId) {
        try {
            const session = sessionManager.sessions.get(sessionId);
            if (!session) {
                throw new Error('Session not found');
            }
            
            console.log(`Processing text query: ${question}`);
            
            // Use enhanced semantic search
            const relevantVerses = await this.knowledgeBase.findRelevantVerses(question, 2);
            
            // Generate response
            const krishnaResponse = await this.generateKrishnaResponse(question, relevantVerses, session);
            
            // Update session
            session.conversationHistory.push({
                timestamp: Date.now(),
                userQuestion: question,
                krishnaResponse: krishnaResponse,
                versesUsed: relevantVerses ? relevantVerses.map(v => v.id) : [],
                type: 'text'
            });
            
            return {
                response: krishnaResponse,
                versesUsed: relevantVerses || [],
                searchMetrics: {
                    queryProcessed: true,
                    versesFound: relevantVerses ? relevantVerses.length : 0,
                    searchType: 'semantic'
                }
            };
            
        } catch (error) {
            console.error('Error processing text query:', error);
            throw error;
        }
    }
    
    cancelActiveRequests(sessionId) {
        for (const [requestId, controller] of this.activeRequests.entries()) {
            if (requestId.includes(sessionId)) {
                controller.abort();
                this.activeRequests.delete(requestId);
            }
        }
        console.log(`Cancelled active requests for session: ${sessionId}`);
    }
}

// Initialize components
let knowledgeBase;
let sessionManager;
let speechProcessor;

// Initialize everything asynchronously
async function initializeServer() {
    try {
        console.log('🚀 Initializing Paarth - Krishna AI Voice Assistant...');
        
        // Validate environment variables first
        if (!process.env.GEMINI_API_KEY) {
            throw new Error('GEMINI_API_KEY not found in environment variables');
        }
        
        // Initialize Gemini AI
        genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
        
        // Initialize enhanced knowledge base with semantic search
        knowledgeBase = new EnhancedKrishnaKnowledgeBase(process.env.GEMINI_API_KEY);
        await knowledgeBase.initialize();
        
        // Initialize other components
        sessionManager = new KrishnaSessionManager();
        speechProcessor = new KrishnaSpeechProcessor(knowledgeBase);
        
        console.log('✅ All components initialized successfully');
        
    } catch (error) {
        console.error('❌ Error initializing server:', error);
        process.exit(1);
    }
}

// Health check endpoint (should be early in the middleware chain)
app.get('/health', (req, res) => {
    const stats = knowledgeBase ? knowledgeBase.getStats() : { status: 'initializing' };
    const activeSessions = sessionManager ? sessionManager.sessions.size : 0;
    
    res.json({ 
        status: 'OK',
        service: 'Paarth - Krishna AI Voice Assistant (Enhanced)',
        version: '2.0.0',
        timestamp: new Date().toISOString(),
        activeSessions: activeSessions,
        knowledgeBase: stats,
        features: {
            semanticSearch: true,
            embeddings: true,
            advancedSearch: true,
            multilingualSupport: true
        }
    });
});

// Root endpoint
app.get('/', (req, res) => {
    res.json({
        message: 'पार्थ - Krishna AI Voice Assistant',
        version: '2.0.0',
        endpoints: {
            websocket: '/ws',
            health: '/health',
            api: '/api/krishna/*'
        }
    });
});

// WebSocket connection handling
wss.on('connection', (ws, req) => {
    console.log(`Paarth client connected from ${req.socket.remoteAddress}`);
    
    const session = sessionManager.createSession(ws);
    
    // Send Krishna's greeting with knowledge base stats
    const stats = knowledgeBase ? knowledgeBase.getStats() : {};
    ws.send(JSON.stringify({
        type: 'connection_established',
        message: 'पार्थ, मैं कृष्ण हूं। आपका स्वागत है।',
        sessionId: session.id,
        knowledgeBaseStats: stats
    }));
    
    ws.on('message', async (message) => {
        try {
            let data;
            try {
                data = JSON.parse(message);
            } catch (parseError) {
                console.error('Invalid JSON received:', parseError);
                ws.send(JSON.stringify({
                    type: 'error',
                    message: 'Invalid message format'
                }));
                return;
            }
            
            const session = sessionManager.getSession(ws);
            
            if (!session) {
                ws.send(JSON.stringify({
                    type: 'error',
                    message: 'Session not found'
                }));
                return;
            }
            
            sessionManager.updateActivity(session.id);
            
            switch (data.type) {
                case 'audio_data':
                    try {
                        if (!data.audio) {
                            throw new Error('No audio data provided');
                        }
                        
                        console.log(`Processing Krishna audio for session: ${session.id}`);
                        
                        const startTime = Date.now();
                        const result = await speechProcessor.processAudio(data.audio, session.id);
                        const processingTime = Date.now() - startTime;
                        
                        console.log(`Krishna responded in ${processingTime}ms`);
                        
                        ws.send(JSON.stringify({
                            type: 'text_response',
                            text: result.response,
                            transcription: result.transcription,
                            versesUsed: result.versesUsed,
                            processingTime: processingTime,
                            sessionId: session.id,
                            speaker: 'krishna'
                        }));
                        
                    } catch (error) {
                        console.error('Error processing Krishna audio:', error);
                        ws.send(JSON.stringify({
                            type: 'error',
                            message: 'वत्स, फिर से बोलकर देखें।'
                        }));
                    }
                    break;
                    
                case 'text_query':
                    try {
                        if (!data.query) {
                            throw new Error('No query provided');
                        }
                        
                        console.log(`Processing text query for session: ${session.id}`);
                        
                        const startTime = Date.now();
                        const result = await speechProcessor.processTextQuery(data.query, session.id);
                        const processingTime = Date.now() - startTime;
                        
                        ws.send(JSON.stringify({
                            type: 'text_response',
                            text: result.response,
                            versesUsed: result.versesUsed,
                            searchMetrics: result.searchMetrics,
                            processingTime: processingTime,
                            sessionId: session.id,
                            speaker: 'krishna'
                        }));
                        
                    } catch (error) {
                        console.error('Error processing text query:', error);
                        ws.send(JSON.stringify({
                            type: 'error',
                            message: 'वत्स, फिर से प्रश्न पूछें।'
                        }));
                    }
                    break;
                    
                case 'get_random_verse':
                    try {
                        const randomVerse = knowledgeBase.getRandomVerse();
                        
                        ws.send(JSON.stringify({
                            type: 'random_verse',
                            verse: randomVerse,
                            sessionId: session.id
                        }));
                        
                    } catch (error) {
                        console.error('Error getting random verse:', error);
                        ws.send(JSON.stringify({
                            type: 'error',
                            message: 'श्लोक प्राप्त करने में समस्या।'
                        }));
                    }
                    break;
                    
                case 'advanced_search':
                    try {
                        const results = await knowledgeBase.advancedSearch(data.options);
                        
                        ws.send(JSON.stringify({
                            type: 'search_results',
                            results: results,
                            searchOptions: data.options,
                            sessionId: session.id
                        }));
                        
                    } catch (error) {
                        console.error('Error in advanced search:', error);
                        ws.send(JSON.stringify({
                            type: 'error',
                            message: 'खोज में समस्या आई।'
                        }));
                    }
                    break;
                    
                case 'ping':
                    ws.send(JSON.stringify({
                        type: 'pong',
                        timestamp: Date.now()
                    }));
                    break;
                    
                default:
                    ws.send(JSON.stringify({
                        type: 'error',
                        message: 'अज्ञात संदेश प्रकार',
                        sessionId: session.id
                    }));
            }
        } catch (error) {
            console.error('Error handling WebSocket message:', error);
            ws.send(JSON.stringify({
                type: 'error',
                message: 'संदेश प्रसंस्करण में त्रुटि'
            }));
        }
    });
    
    ws.on('pong', () => {
        const session = sessionManager.getSession(ws);
        if (session) {
            sessionManager.updateActivity(session.id);
        }
    });
    
    ws.on('close', () => {
        const session = sessionManager.getSession(ws);
        if (session) {
            speechProcessor.cancelActiveRequests(session.id);
            
            const sessionDuration = Date.now() - session.startTime;
            console.log(`Krishna session ended: ${session.id}, Duration: ${Math.round(sessionDuration/1000)}s, Questions: ${session.conversationHistory.length}`);
        }
        
        sessionManager.removeSession(ws);
    });
    
    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
        const session = sessionManager.getSession(ws);
        if (session) {
            speechProcessor.cancelActiveRequests(session.id);
        }
    });
});

// Enhanced API endpoints
app.get('/api/krishna/verses', async (req, res) => {
    try {
        const { chapter, random, limit = 10 } = req.query;
        
        if (random === 'true') {
            const verse = knowledgeBase.getRandomVerse();
            return res.json({ verse });
        }
        
        if (chapter) {
            const verses = knowledgeBase.getVersesByChapter(parseInt(chapter));
            return res.json({ verses: verses.slice(0, limit) });
        }
        
        // Return all verses with limit
        const allVerses = knowledgeBase.verses.slice(0, parseInt(limit));
        res.json({ verses: allVerses, total: knowledgeBase.verses.length });
        
    } catch (error) {
        res.status(500).json({ error: 'Error fetching verses', message: error.message });
    }
});

app.post('/api/krishna/search', async (req, res) => {
    try {
        const { query, maxResults = 3 } = req.body;
        
        if (!query) {
            return res.json({ verses: [], message: 'No query provided' });
        }
        
        const startTime = Date.now();
        const relevantVerses = await knowledgeBase.findRelevantVerses(query, parseInt(maxResults));
        const searchTime = Date.now() - startTime;
        
        res.json({ 
            query: query,
            verses: relevantVerses,
            count: relevantVerses.length,
            searchTime: searchTime,
            searchType: 'semantic_embedding'
        });
        
    } catch (error) {
        res.status(500).json({ error: 'Search failed', message: error.message });
    }
});

app.post('/api/krishna/advanced-search', async (req, res) => {
    try {
        const searchOptions = req.body;
        
        const startTime = Date.now();
        const results = await knowledgeBase.advancedSearch(searchOptions);
        const searchTime = Date.now() - startTime;
        
        res.json({
            results: results,
            searchOptions: searchOptions,
            count: results.length,
            searchTime: searchTime
        });
        
    } catch (error) {
        res.status(500).json({ error: 'Advanced search failed', message: error.message });
    }
});

app.post('/api/krishna/ask', async (req, res) => {
    try {
        const { question, sessionId } = req.body;
        
        if (!question) {
            return res.status(400).json({ error: 'Question is required' });
        }
        
        // Create temporary session if not provided
        let session;
        if (sessionId && sessionManager.sessions.has(sessionId)) {
            session = sessionManager.sessions.get(sessionId);
        } else {
            session = {
                id: `temp_${Date.now()}`,
                conversationHistory: []
            };
        }
        
        const result = await speechProcessor.processTextQuery(question, session.id);
        
        res.json({
            question: question,
            response: result.response,
            versesUsed: result.versesUsed,
            searchMetrics: result.searchMetrics,
            sessionId: session.id
        });
        
    } catch (error) {
        res.status(500).json({ error: 'Failed to process question', message: error.message });
    }
});

// Knowledge base management endpoints
app.get('/api/krishna/stats', (req, res) => {
    const stats = knowledgeBase ? knowledgeBase.getStats() : {};
    const activeSessions = sessionManager ? sessionManager.sessions.size : 0;
    const totalConversations = sessionManager ? Array.from(sessionManager.sessions.values())
        .reduce((sum, s) => sum + s.conversationHistory.length, 0) : 0;
    
    res.json({ 
        knowledgeBase: stats,
        server: {
            activeSessions: activeSessions,
            totalConversations: totalConversations,
            uptime: process.uptime()
        }
    });
});

// Session analytics
app.get('/api/krishna/sessions', (req, res) => {
    if (!sessionManager) {
        return res.status(503).json({ error: 'Server not fully initialized' });
    }
    
    const sessions = Array.from(sessionManager.sessions.entries()).map(([id, session]) => ({
        id: id,
        duration: Date.now() - session.startTime,
        lastActivity: session.lastActivity,
        questionCount: session.conversationHistory.length,
        devotionalLevel: session.devotionalLevel
    }));
    
    res.json({ sessions });
});

// Cleanup inactive sessions
setInterval(() => {
    if (!sessionManager) return;
    
    const now = Date.now();
    const timeoutMs = 20 * 60 * 1000; // 20 minutes timeout
    
    for (const [sessionId, session] of sessionManager.sessions.entries()) {
        if (now - session.lastActivity > timeoutMs) {
            console.log(`Cleaning up inactive Krishna session: ${sessionId}`);
            if (speechProcessor) {
                speechProcessor.cancelActiveRequests(sessionId);
            }
            sessionManager.sessions.delete(sessionId);
            
            if (session.ws && session.ws.readyState === WebSocket.OPEN) {
                session.ws.close();
            }
        }
    }
}, 5 * 60 * 1000); // Check every 5 minutes

// Error handling middleware
app.use((error, req, res, next) => {
    console.error('Server error:', error);
    res.status(500).json({
        error: 'सर्वर में समस्या है',
        message: error.message
    });
});

// 404 handler
app.use('*', (req, res) => {
    res.status(404).json({
        error: 'पथ नहीं मिला',
        message: 'यह URL उपलब्ध नहीं है'
    });
});

// Environment variables with defaults for Fly.io
const PORT = process.env.PORT || 8080;
const HOST = '0.0.0.0'; // Always bind to 0.0.0.0 for Fly.io

// Start server after initialization
initializeServer().then(() => {
    server.listen(PORT, HOST, () => {
        console.log(`🪶 पार्थ - Krishna AI Voice Assistant (Enhanced)`);
        console.log(`🌐 Server running on http://${HOST}:${PORT}`);
        console.log(`🚁 Fly.io deployment ready on port ${PORT}`);
        
        if (knowledgeBase) {
            const stats = knowledgeBase.getStats();
            console.log(`📿 ${stats.totalVerses || 0} Gita verses loaded with semantic search`);
            console.log(`🧠 ${stats.versesWithEmbeddings || 0} verses with embeddings`);
        }
        
        console.log(`🕉️  Ready to serve divine wisdom with AI-powered relevance`);
        
        // Validate required environment variables
        if (!process.env.GEMINI_API_KEY) {
            console.error('❌ GEMINI_API_KEY not found in environment variables');
            console.log('📝 Please add GEMINI_API_KEY to your .env file or Fly.io secrets');
        } else {
            console.log('✅ Gemini AI configured for embeddings and responses');
        }
        
        console.log(`🔧 Environment: ${process.env.NODE_ENV || 'development'}`);
    });
}).catch(error => {
    console.error('❌ Failed to initialize server:', error);
    process.exit(1);
});

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('🙏 Krishna assistant shutting down gracefully...');
    
    // Close all WebSocket connections
    if (sessionManager) {
        for (const [sessionId, session] of sessionManager.sessions.entries()) {
            if (speechProcessor) {
                speechProcessor.cancelActiveRequests(sessionId);
            }
            if (session.ws && session.ws.readyState === WebSocket.OPEN) {
                session.ws.send(JSON.stringify({
                    type: 'server_shutdown',
                    message: 'सर्वर बंद हो रहा है। कृपया पुनः कनेक्ट करें।'
                }));
                session.ws.close();
            }
        }
    }
    
    server.close(() => {
        console.log('✅ Server closed');
        process.exit(0);
    });
});

process.on('SIGINT', () => {
    console.log('🙏 Krishna assistant received SIGINT, shutting down gracefully...');
    process.emit('SIGTERM');
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error);
    process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection at:', promise, 'reason:', reason);
    process.exit(1);
});

module.exports = {
    app,
    server,
    knowledgeBase,
    sessionManager,
    speechProcessor
};