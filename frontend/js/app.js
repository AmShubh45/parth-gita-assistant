/**
 * Paarth Krishna Assistant — Frontend Application
 *
 * Handles WebSocket communication, audio recording, text-to-speech,
 * and UI interactions for the Krishna voice assistant.
 */

class PaarthKrishnaAssistant {
    constructor() {
        this.ws = null;
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.currentTTS = null;
        this.volume = 0.8;
        this.isConnected = false;
        this.isProcessing = false;

        this.initializeWebSocket();
        this.initializeSpeechSynthesis();
    }

    initializeWebSocket() {
        try {
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            this.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            this.ws.onopen = () => {
                this.isConnected = true;
                this.updateConnectionStatus(true);
                this.updateStatus('🟢 कृष्ण से जुड़ाव सफल! अब बोलें...');
                this.speakKrishnaMessage('प्रणाम पार्थ! मैं कृष्ण हूं। आपकी सेवा में उपस्थित हूं।');
            };

            this.ws.onmessage = (event) => {
                this.handleWebSocketMessage(JSON.parse(event.data));
            };

            this.ws.onclose = () => {
                this.isConnected = false;
                this.updateConnectionStatus(false);
                this.updateStatus('❌ कनेक्शन टूट गया। पेज रीफ्रेश करें।');
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateStatus('❌ कनेक्शन में समस्या है।');
            };

        } catch (error) {
            console.error('WebSocket initialization failed:', error);
            this.updateStatus('❌ सर्वर से जुड़ नहीं पा रहे।');
        }
    }

    handleWebSocketMessage(data) {
        this.hideLoading();

        switch (data.type) {
            case 'connection_established':
                this.addKrishnaResponse('🙏 प्रणाम! मैं कृष्ण हूं। आपकी हर समस्या का समाधान गीता में है।');
                break;

            case 'text_response':
                this.addKrishnaResponse(data.text);
                this.speakKrishnaMessage(data.text);
                this.updateStatus('🎤 अगला प्रश्न बोलें...');
                break;

            case 'random_verse':
                this.displayVerse(data.verse);
                break;

            case 'error':
                this.updateStatus(`❌ ${data.message}`);
                break;
        }
    }

    async startRecording() {
        if (!this.isConnected || this.isProcessing) return;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 44100,
                    channelCount: 1
                }
            });

            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.audioChunks = [];
            this.isRecording = true;

            this.updateVoiceButton(true);
            this.showAudioVisualizer(true);
            this.updateStatus('🎙️ सुन रहा हूं... बोलें');

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.sendAudioToKrishna(audioBlob);

                // Stop all tracks
                stream.getTracks().forEach(track => track.stop());

                this.showAudioVisualizer(false);
                this.updateVoiceButton(false);
                this.updateStatus('🤔 कृष्ण सोच रहे हैं...');
            };

            this.mediaRecorder.start();

            // Auto-stop after 30 seconds
            setTimeout(() => {
                if (this.isRecording) {
                    this.stopRecording();
                }
            }, 30000);

        } catch (error) {
            console.error('Error starting recording:', error);
            this.updateStatus('❌ माइक्रोफोन की अनुमति चाहिए।');
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
        }
    }

    async sendAudioToKrishna(audioBlob) {
        try {
            this.isProcessing = true;
            this.showLoading();

            const reader = new FileReader();
            reader.onloadend = () => {
                const base64Audio = reader.result.split(',')[1];

                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'audio_data',
                        audio: base64Audio,
                        context: 'krishna_conversation'
                    }));
                }
            };
            reader.readAsDataURL(audioBlob);

        } catch (error) {
            console.error('Error sending audio:', error);
            this.hideLoading();
            this.isProcessing = false;
            this.updateStatus('❌ ऑडियो भेजने में समस्या।');
        }
    }

    speakKrishnaMessage(text) {
        try {
            this.stopSpeaking();

            if (!window.speechSynthesis) {
                console.warn('Text-to-Speech not supported');
                return;
            }

            // Clean the text for better TTS
            let cleanText = text
                .replace(/[🙏🪶📿🕉️🎤🔊]/g, '')
                .replace(/॥.*॥/g, '')
                .replace(/\*.*\*/g, '')
                .trim();

            this.currentTTS = new SpeechSynthesisUtterance(cleanText);
            this.currentTTS.lang = 'hi-IN';
            this.currentTTS.volume = this.volume;
            this.currentTTS.rate = 0.85;
            this.currentTTS.pitch = 0.9;

            // Try to find best Hindi voice
            const voices = speechSynthesis.getVoices();
            const hindiVoice = voices.find(voice =>
                voice.lang === 'hi-IN' ||
                voice.lang.startsWith('hi') ||
                voice.name.toLowerCase().includes('hindi')
            );

            if (hindiVoice) {
                this.currentTTS.voice = hindiVoice;
            }

            this.currentTTS.onstart = () => {
                document.getElementById('stopBtn').style.display = 'inline-block';
                this.updateStatus('🗣️ कृष्ण बोल रहे हैं...');
            };

            this.currentTTS.onend = () => {
                document.getElementById('stopBtn').style.display = 'none';
                this.updateStatus('🎤 अगला प्रश्न बोलें...');
                this.currentTTS = null;
                this.isProcessing = false;
            };

            this.currentTTS.onerror = (error) => {
                console.error('TTS Error:', error);
                document.getElementById('stopBtn').style.display = 'none';
                this.isProcessing = false;
            };

            speechSynthesis.speak(this.currentTTS);

        } catch (error) {
            console.error('Error in Text-to-Speech:', error);
            this.isProcessing = false;
        }
    }

    stopSpeaking() {
        if (speechSynthesis.speaking) {
            speechSynthesis.cancel();
        }
        if (this.currentTTS) {
            this.currentTTS = null;
        }
        document.getElementById('stopBtn').style.display = 'none';
    }

    addKrishnaResponse(text) {
        const responseArea = document.getElementById('responseArea');

        const messageDiv = document.createElement('div');
        messageDiv.className = 'krishna-message';

        const formattedText = this.formatKrishnaResponse(text);
        messageDiv.innerHTML = formattedText;

        responseArea.appendChild(messageDiv);
        responseArea.scrollTop = responseArea.scrollHeight;
    }

    formatKrishnaResponse(text) {
        let formatted = text;

        // Add Krishna greeting if not present
        if (!text.includes('॥') && !text.includes('कृष्ण')) {
            formatted = '<div class="krishna-greeting">॥ श्री कृष्ण कहते हैं ॥</div>' + formatted;
        }

        // Format Sanskrit verses
        formatted = formatted.replace(
            /([\u0900-\u097F\s]+॥|॥[\u0900-\u097F\s]+)/g,
            '<div class="verse-section"><div class="sanskrit-text">$1</div></div>'
        );

        // Format references to Gita chapters/verses
        formatted = formatted.replace(
            /(अध्याय \d+[,\s]*श्लोक \d+)/g,
            '<strong style="color: #ffd700;">$1</strong>'
        );

        return formatted;
    }

    displayVerse(verse) {
        const verseHtml = `
            <div class="krishna-greeting">॥ आज का श्लोक ॥</div>
            <div class="verse-section">
                <strong style="color: #ffd700;">अध्याय ${verse.chapter}, श्लोक ${verse.verse}</strong><br><br>
                <div class="sanskrit-text">${verse.sanskrit}</div><br>
                <strong>अर्थ:</strong> ${verse.hindi}<br><br>
                <strong>व्याख्या:</strong> ${verse.meaning}
            </div>
        `;

        this.addKrishnaResponse(verseHtml);

        const spokenText = `अध्याय ${verse.chapter}, श्लोक ${verse.verse}. ${verse.hindi}. ${verse.meaning}`;
        this.speakKrishnaMessage(spokenText);
    }

    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connectionStatus');
        const span = statusEl.querySelector('span');

        if (connected) {
            span.textContent = '🟢 कृष्ण से जुड़े';
            span.className = 'connected';
        } else {
            span.textContent = '🔴 कनेक्शन नहीं';
            span.className = 'disconnected';
        }
    }

    updateVoiceButton(recording) {
        const button = document.getElementById('voiceButton');
        const icon = button.querySelector('.mic-icon');

        if (recording) {
            button.classList.add('listening');
            icon.textContent = '⏸️';
        } else {
            button.classList.remove('listening');
            icon.textContent = '🎤';
        }
    }

    showAudioVisualizer(show) {
        const visualizer = document.getElementById('audioVisualizer');
        if (show) {
            visualizer.classList.add('show');
        } else {
            visualizer.classList.remove('show');
        }
    }

    updateStatus(text) {
        document.getElementById('statusText').textContent = text;
    }

    showLoading() {
        document.getElementById('loadingSpinner').classList.add('show');
    }

    hideLoading() {
        document.getElementById('loadingSpinner').classList.remove('show');
    }

    initializeSpeechSynthesis() {
        // Load voices when available
        if (speechSynthesis.onvoiceschanged !== undefined) {
            speechSynthesis.onvoiceschanged = () => {
                const voices = speechSynthesis.getVoices();
                console.log('Available voices for Krishna:', voices.filter(v => v.lang.startsWith('hi')));
            };
        }

        // Initial greeting
        setTimeout(() => {
            if (this.isConnected) {
                this.speakKrishnaMessage('नमस्कार पार्थ! मैं कृष्ण हूं। आपका स्वागत है।');
            }
        }, 2000);
    }

    setVolume(volume) {
        this.volume = parseFloat(volume);
        if (this.currentTTS) {
            this.currentTTS.volume = this.volume;
        }
    }

    getRandomVerse() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'get_random_verse' }));
        }
    }

    clearConversation() {
        document.getElementById('responseArea').innerHTML = `
            <div class="krishna-message">
                <div class="krishna-greeting">॥ श्री कृष्ण कहते हैं ॥</div>
                प्रिय पार्थ, मैं यहां आपके हर प्रश्न का उत्तर देने के लिए हूं। जीवन की कोई भी चुनौती हो, धर्म की कोई भी उलझन हो, या मन में कोई भी दुविधा हो - निःसंकोच पूछें। गीता का ज्ञान सदैव आपके साथ है।
                <div class="verse-section">
                    <div class="sanskrit-text">सर्वधर्मान्परित्यज्य मामेकं शरणं व्रज</div>
                    सभी धर्मों को छोड़कर मेरी शरण में आओ
                </div>
            </div>
        `;
        this.updateStatus('🎤 नया प्रश्न बोलें...');
    }
}

// ── Global Instance & Functions ────────────────────────────────────────────

let krishnaAssistant;

function toggleVoiceRecording() {
    if (krishnaAssistant.isRecording) {
        krishnaAssistant.stopRecording();
    } else {
        krishnaAssistant.startRecording();
    }
}

function setVolume(volume) {
    krishnaAssistant.setVolume(volume);
}

function stopSpeaking() {
    krishnaAssistant.stopSpeaking();
}

function getRandomVerse() {
    krishnaAssistant.getRandomVerse();
}

function clearConversation() {
    krishnaAssistant.clearConversation();
}

// Initialize when page loads
window.addEventListener('DOMContentLoaded', () => {
    krishnaAssistant = new PaarthKrishnaAssistant();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden && krishnaAssistant?.isRecording) {
        krishnaAssistant.stopRecording();
    }
});

// Handle before unload
window.addEventListener('beforeunload', () => {
    if (krishnaAssistant?.isRecording) {
        krishnaAssistant.stopRecording();
    }
    krishnaAssistant?.stopSpeaking();
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        toggleVoiceRecording();
    }
    if (e.key === 'Escape') {
        stopSpeaking();
    }
});

document.addEventListener('keyup', (e) => {
    if (e.code === 'Space') {
        e.preventDefault();
        if (krishnaAssistant?.isRecording) {
            krishnaAssistant.stopRecording();
        }
    }
});
