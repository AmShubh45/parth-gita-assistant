const { GoogleGenerativeAI } = require('@google/generative-ai');
const WebSocket = require('ws');

class GeminiLiveIntegration {
    constructor(apiKey, systemInstructions) {
        this.genAI = new GoogleGenerativeAI(apiKey);
        this.systemInstructions = systemInstructions;
        this.activeConnections = new Map();
    }
    
    async createLiveSession(connectionId, modelName = 'gemini-2.0-flash-live-001') {
        try {
            const model = this.genAI.getGenerativeModel({
                model: modelName,
                systemInstruction: this.systemInstructions,
                generationConfig: {
                    temperature: 0.7,
                    topP: 0.8,
                    topK: 40,
                    maxOutputTokens: 1024,
                }
            });
            
            // Initialize chat session
            const chatSession = model.startChat({
                history: [],
            });
            
            this.activeConnections.set(connectionId, {
                model,
                chatSession,
                isActive: true
            });
            
            return true;
        } catch (error) {
            console.error('Error creating live session:', error);
            return false;
        }
    }
    
    async processAudioInput(connectionId, audioData, mimeType = 'audio/webm') {
        const connection = this.activeConnections.get(connectionId);
        if (!connection || !connection.isActive) {
            throw new Error('No active session found');
        }
        
        try {
            const startTime = Date.now();
            
            // Send audio data to Gemini
            const result = await connection.chatSession.sendMessage({
                inlineData: {
                    mimeType: mimeType,
                    data: audioData
                }
            });
            
            const response = await result.response;
            const latency = Date.now() - startTime;
            
            console.log(`Response latency: ${latency}ms`);
            
            // Extract audio response if available
            const candidate = response.candidates?.[0];
            if (candidate?.content?.parts?.[0]?.inlineData) {
                return {
                    success: true,
                    audioData: candidate.content.parts[0].inlineData.data,
                    mimeType: candidate.content.parts[0].inlineData.mimeType,
                    latency
                };
            }
            
            // Fallback to text response
            const textResponse = candidate?.content?.parts?.[0]?.text;
            if (textResponse) {
                // Convert text to speech using system TTS or return text
                return {
                    success: true,
                    textResponse,
                    latency
                };
            }
            
            throw new Error('No valid response received');
            
        } catch (error) {
            console.error('Error processing audio input:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    async processTextInput(connectionId, text) {
        const connection = this.activeConnections.get(connectionId);
        if (!connection || !connection.isActive) {
            throw new Error('No active session found');
        }
        
        try {
            const startTime = Date.now();
            
            const result = await connection.chatSession.sendMessage(text);
            const response = await result.response;
            const latency = Date.now() - startTime;
            
            const textResponse = response.text();
            
            return {
                success: true,
                textResponse,
                latency
            };
            
        } catch (error) {
            console.error('Error processing text input:', error);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    interruptSession(connectionId) {
        const connection = this.activeConnections.get(connectionId);
        if (!connection || !connection.isActive) {
            return false;
        }
        
        try {
            // Mark session as interrupted
            connection.interrupted = true;
            
            // In a real implementation, you would stop any ongoing generation
            // For now, we'll just mark it as interrupted
            console.log(`Session ${connectionId} interrupted`);
            
            return true;
        } catch (error) {
            console.error('Error interrupting session:', error);
            return false;
        }
    }
    
    endSession(connectionId) {
        const connection = this.activeConnections.get(connectionId);
        if (connection) {
            connection.isActive = false;
            this.activeConnections.delete(connectionId);
            console.log(`Session ${connectionId} ended`);
            return true;
        }
        return false;
    }
    
    getActiveSessionsCount() {
        return this.activeConnections.size;
    }
    
    // Text-to-speech fallback using Web Speech API simulation
    async textToSpeech(text, voice = 'en-US') {
        // This is a placeholder for TTS functionality
        // In a real implementation, you might use:
        // - Google Cloud Text-to-Speech API
        // - Azure Cognitive Services Speech
        // - AWS Polly
        // - Or handle it on the client side
        
        return {
            success: true,
            audioData: null, // Would contain base64 audio data
            mimeType: 'audio/wav',
            message: 'TTS not implemented - handle on client side'
        };
    }
}

module.exports = GeminiLiveIntegration;