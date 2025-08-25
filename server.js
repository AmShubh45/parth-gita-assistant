const express = require('express');
const WebSocket = require('ws');
const http = require('http');
const path = require('path');
const { GoogleGenerativeAI } = require('@google/generative-ai');
require('dotenv').config();

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Serve static files
app.use(express.static('public'));
app.use(express.json());

// Enhanced system instructions for Revolt Motors
const SYSTEM_INSTRUCTIONS = `You are Rev, the official voice assistant for Revolt Motors, India's leading electric motorcycle company. 

COMPANY OVERVIEW:
- Founded in 2019 by Rahul Sharma (former co-founder of Micromax)
- India's first AI-enabled electric motorcycle manufacturer
- Mission: Accelerating India's transition to sustainable mobility

PRODUCTS:
RV400: ₹1.38 lakhs, 150km range, 85 kmph top speed, 0-40 in 3.24s
RV300: ₹1.18 lakhs, 150km range, 65 kmph top speed

KEY FEATURES: Swappable batteries, MyRevolt app, 4 riding modes, artificial sound system

IMPORTANT: Keep responses conversational, concise (1-2 sentences), and enthusiastic about electric mobility. Redirect off-topic questions back to Revolt Motors. Be prepared to handle interruptions gracefully - if interrupted, provide shorter responses when the conversation resumes.`;

// Initialize Gemini AI
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

// Session management
class SessionManager {
    constructor() {
        this.sessions = new Map();
    }
    
    createSession(ws) {
        const sessionId = Date.now().toString();
        const session = {
            id: sessionId,
            ws: ws,
            isActive: false,
            isProcessing: false,
            lastActivity: Date.now(),
            interruptCount: 0,
            conversationHistory: []
        };
        
        this.sessions.set(sessionId, session);
        ws.sessionId = sessionId;
        
        console.log(`Session created: ${sessionId}`);
        return session;
    }
    
    getSession(ws) {
        return this.sessions.get(ws.sessionId);
    }
    
    updateActivity(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.lastActivity = Date.now();
        }
    }
    
    removeSession(ws) {
        if (ws.sessionId) {
            this.sessions.delete(ws.sessionId);
            console.log(`Session removed: ${ws.sessionId}`);
        }
    }
    
    handleInterrupt(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.interruptCount++;
            session.isProcessing = false;
            this.updateActivity(sessionId);
            console.log(`Session ${sessionId} interrupted (count: ${session.interruptCount})`);
        }
    }
}

const sessionManager = new SessionManager();

// Enhanced Speech processor with interruption handling
class SpeechProcessor {
    constructor() {
        this.model = genAI.getGenerativeModel({
            model: "gemini-1.5-flash",
            systemInstruction: SYSTEM_INSTRUCTIONS
        });
        this.activeRequests = new Map();
    }
    
    async processAudio(base64Audio, sessionId) {
        const requestId = Date.now().toString();
        
        try {
            // Store the request for potential cancellation
            const abortController = new AbortController();
            this.activeRequests.set(requestId, abortController);
            
            const session = sessionManager.sessions.get(sessionId);
            if (!session) {
                throw new Error('Session not found');
            }
            
            session.isProcessing = true;
            
            // Add context about interruptions if they've occurred
            let contextPrompt = "Please transcribe this audio and respond as Rev, the Revolt Motors assistant:";
            if (session.interruptCount > 0) {
                contextPrompt += " (Note: User has interrupted before, so keep response brief and direct)";
            }
            
            const result = await this.model.generateContent([
                contextPrompt,
                {
                    inlineData: {
                        mimeType: "audio/webm",
                        data: base64Audio
                    }
                }
            ]);
            
            // Check if request was cancelled during processing
            if (this.activeRequests.has(requestId)) {
                const response = await result.response;
                const responseText = response.text();
                
                // Store in conversation history
                session.conversationHistory.push({
                    timestamp: Date.now(),
                    type: 'user_audio',
                    processed: true
                });
                
                session.conversationHistory.push({
                    timestamp: Date.now(),
                    type: 'assistant_response',
                    text: responseText
                });
                
                session.isProcessing = false;
                this.activeRequests.delete(requestId);
                
                return responseText;
            } else {
                // Request was cancelled
                session.isProcessing = false;
                throw new Error('Request was interrupted');
            }
            
        } catch (error) {
            session.isProcessing = false;
            this.activeRequests.delete(requestId);
            console.error('Error processing audio:', error);
            throw error;
        }
    }
    
    async processText(text, sessionId) {
        const requestId = Date.now().toString();
        
        try {
            const abortController = new AbortController();
            this.activeRequests.set(requestId, abortController);
            
            const session = sessionManager.sessions.get(sessionId);
            if (!session) {
                throw new Error('Session not found');
            }
            
            session.isProcessing = true;
            
            // Add context for brief responses if user interrupts frequently
            let enhancedPrompt = text;
            if (session.interruptCount > 2) {
                enhancedPrompt = `${text} (Please provide a very brief, direct response as the user seems to prefer shorter interactions)`;
            }
            
            const result = await this.model.generateContent(enhancedPrompt);
            
            if (this.activeRequests.has(requestId)) {
                const response = await result.response;
                const responseText = response.text();
                
                // Store in conversation history
                session.conversationHistory.push({
                    timestamp: Date.now(),
                    type: 'user_text',
                    text: text
                });
                
                session.conversationHistory.push({
                    timestamp: Date.now(),
                    type: 'assistant_response',
                    text: responseText
                });
                
                session.isProcessing = false;
                this.activeRequests.delete(requestId);
                
                return responseText;
            } else {
                session.isProcessing = false;
                throw new Error('Request was interrupted');
            }
            
        } catch (error) {
            session.isProcessing = false;
            this.activeRequests.delete(requestId);
            console.error('Error processing text:', error);
            throw error;
        }
    }
    
    cancelActiveRequests(sessionId) {
        // Cancel all active requests for a session
        for (const [requestId, controller] of this.activeRequests.entries()) {
            controller.abort();
            this.activeRequests.delete(requestId);
        }
        
        const session = sessionManager.sessions.get(sessionId);
        if (session) {
            session.isProcessing = false;
        }
        
        console.log(`Cancelled active requests for session: ${sessionId}`);
    }
}

const speechProcessor = new SpeechProcessor();

// Enhanced WebSocket connection handling
wss.on('connection', (ws) => {
    console.log('Client connected');
    
    // Create session for this connection
    const session = sessionManager.createSession(ws);
    
    // Send connection confirmation
    ws.send(JSON.stringify({
        type: 'connection_established',
        sessionId: session.id,
        message: 'Connected to Rev assistant'
    }));
    
    ws.on('message', async (message) => {
        try {
            const data = JSON.parse(message);
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
                case 'start_session':
                    try {
                        session.isActive = true;
                        session.interruptCount = 0; // Reset interrupt count
                        session.conversationHistory = []; // Reset conversation
                        
                        ws.send(JSON.stringify({
                            type: 'session_started',
                            message: 'Voice session started',
                            sessionId: session.id
                        }));
                        
                        console.log(`Session ${session.id} started`);
                    } catch (error) {
                        console.error('Error starting session:', error);
                        ws.send(JSON.stringify({
                            type: 'error',
                            message: 'Failed to start session'
                        }));
                    }
                    break;
                    
                case 'audio_data':
                    try {
                        if (!session.isActive) {
                            ws.send(JSON.stringify({
                                type: 'error',
                                message: 'Session not active'
                            }));
                            return;
                        }
                        
                        console.log(`Processing audio data for session ${session.id}...`);
                        const startTime = Date.now();
                        
                        // Cancel any ongoing requests before processing new audio
                        speechProcessor.cancelActiveRequests(session.id);
                        
                        const responseText = await speechProcessor.processAudio(data.audio, session.id);
                        const processingTime = Date.now() - startTime;
                        
                        console.log(`Audio processed in ${processingTime}ms for session ${session.id}:`, responseText.substring(0, 100) + '...');
                        
                        // Send text response back to client for TTS
                        ws.send(JSON.stringify({
                            type: 'text_response',
                            text: responseText,
                            processingTime: processingTime,
                            sessionId: session.id
                        }));
                        
                    } catch (error) {
                        console.error('Error processing audio:', error);
                        if (error.message !== 'Request was interrupted') {
                            ws.send(JSON.stringify({
                                type: 'error',
                                message: 'Failed to process audio: ' + error.message
                            }));
                        }
                    }
                    break;
                    
                case 'text_message':
                    try {
                        if (!session.isActive) {
                            ws.send(JSON.stringify({
                                type: 'error',
                                message: 'Session not active'
                            }));
                            return;
                        }
                        
                        console.log(`Processing text message for session ${session.id}:`, data.text);
                        const startTime = Date.now();
                        
                        // Cancel any ongoing requests before processing new text
                        speechProcessor.cancelActiveRequests(session.id);
                        
                        const responseText = await speechProcessor.processText(data.text, session.id);
                        const processingTime = Date.now() - startTime;
                        
                        console.log(`Text processed in ${processingTime}ms for session ${session.id}:`, responseText.substring(0, 100) + '...');
                        
                        ws.send(JSON.stringify({
                            type: 'text_response',
                            text: responseText,
                            processingTime: processingTime,
                            sessionId: session.id
                        }));
                        
                    } catch (error) {
                        console.error('Error processing text:', error);
                        if (error.message !== 'Request was interrupted') {
                            ws.send(JSON.stringify({
                                type: 'error',
                                message: 'Failed to process text: ' + error.message
                            }));
                        }
                    }
                    break;
                    
                case 'interrupt':
                    try {
                        console.log(`Handling interrupt for session ${session.id}`);
                        
                        // Cancel all active AI requests
                        speechProcessor.cancelActiveRequests(session.id);
                        
                        // Update session state
                        sessionManager.handleInterrupt(session.id);
                        
                        ws.send(JSON.stringify({
                            type: 'interrupted',
                            message: 'AI interrupted successfully',
                            sessionId: session.id,
                            interruptCount: session.interruptCount
                        }));
                        
                    } catch (error) {
                        console.error('Error handling interruption:', error);
                        ws.send(JSON.stringify({
                            type: 'error',
                            message: 'Failed to handle interruption'
                        }));
                    }
                    break;
                    
                case 'end_session':
                    try {
                        // Cancel any active requests
                        speechProcessor.cancelActiveRequests(session.id);
                        
                        session.isActive = false;
                        session.isProcessing = false;
                        
                        ws.send(JSON.stringify({
                            type: 'session_ended',
                            message: 'Voice session ended',
                            sessionId: session.id,
                            stats: {
                                duration: Date.now() - session.lastActivity,
                                interruptCount: session.interruptCount,
                                conversationLength: session.conversationHistory.length
                            }
                        }));
                        
                        console.log(`Session ${session.id} ended (interrupts: ${session.interruptCount})`);
                        
                    } catch (error) {
                        console.error('Error ending session:', error);
                    }
                    break;
                    
                case 'ping':
                    // Heartbeat/keepalive
                    ws.send(JSON.stringify({
                        type: 'pong',
                        timestamp: Date.now(),
                        sessionId: session.id
                    }));
                    break;
                    
                default:
                    ws.send(JSON.stringify({
                        type: 'error',
                        message: `Unknown message type: ${data.type}`,
                        sessionId: session.id
                    }));
            }
        } catch (error) {
            console.error('Error handling WebSocket message:', error);
            ws.send(JSON.stringify({
                type: 'error',
                message: 'Failed to process message: ' + error.message
            }));
        }
    });
    
    ws.on('close', () => {
        const session = sessionManager.getSession(ws);
        if (session) {
            // Cancel any active requests
            speechProcessor.cancelActiveRequests(session.id);
            console.log(`Client disconnected (session: ${session.id}, interrupts: ${session.interruptCount})`);
        } else {
            console.log('Client disconnected (no session)');
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

// Cleanup inactive sessions periodically
setInterval(() => {
    const now = Date.now();
    const timeoutMs = 30 * 60 * 1000; // 30 minutes
    
    for (const [sessionId, session] of sessionManager.sessions.entries()) {
        if (now - session.lastActivity > timeoutMs) {
            console.log(`Cleaning up inactive session: ${sessionId}`);
            speechProcessor.cancelActiveRequests(sessionId);
            sessionManager.sessions.delete(sessionId);
            
            // Close WebSocket if still open
            if (session.ws.readyState === WebSocket.OPEN) {
                session.ws.close();
            }
        }
    }
}, 5 * 60 * 1000); // Check every 5 minutes

// Health check endpoint with session info
app.get('/health', (req, res) => {
    const activeSessions = sessionManager.sessions.size;
    const activeProcessing = Array.from(sessionManager.sessions.values())
        .filter(s => s.isProcessing).length;
    
    res.json({ 
        status: 'OK', 
        timestamp: new Date().toISOString(),
        activeSessions: activeSessions,
        activeProcessing: activeProcessing,
        totalInterrupts: Array.from(sessionManager.sessions.values())
            .reduce((sum, s) => sum + s.interruptCount, 0)
    });
});

// Session info endpoint
app.get('/sessions', (req, res) => {
    const sessions = Array.from(sessionManager.sessions.entries()).map(([id, session]) => ({
        id: id,
        isActive: session.isActive,
        isProcessing: session.isProcessing,
        lastActivity: session.lastActivity,
        interruptCount: session.interruptCount,
        conversationLength: session.conversationHistory.length
    }));
    
    res.json({ sessions });
});

const PORT = process.env.PORT || 3000;

server.listen(PORT, () => {
    console.log(`Enhanced Rev Assistant server running on port ${PORT}`);
    console.log(`Access the app at http://localhost:${PORT}`);
    console.log('Features: Enhanced interruption handling, session management, conversation tracking');
});