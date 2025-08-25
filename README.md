# Revolt Motors Voice Assistant - Gemini Live Implementation

A real-time conversational voice interface for Revolt Motors using Google's Gemini Live API, replicating the functionality of the original Rev voice chatbot.

## Features

- ✅ **Real-time Voice Conversation**: Low-latency voice interaction using Gemini Live API
- ✅ **Interruption Support**: Users can interrupt the AI mid-response
- ✅ **Server-to-Server Architecture**: Built with Node.js/Express and WebSocket
- ✅ **Revolt Motors Context**: AI assistant trained specifically for Revolt Motors
- ✅ **Modern UI**: Clean, responsive interface with visual feedback
- ✅ **Cross-Platform**: Works on desktop and mobile devices

## Quick Start

### Prerequisites

- Node.js 16+ installed
- Google AI Studio API key (free at [aistudio.google.com](https://aistudio.google.com))

### Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd revolt-voice-chat
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your Gemini API key:
   ```
   GEMINI_API_KEY=your_gemini_api_key_here
   PORT=3000
   ```

4. **Get your API key**:
   - Go to [Google AI Studio](https://aistudio.google.com)
   - Sign in with your Google account
   - Click "Get API key" and create a new key
   - Copy the key to your `.env` file

5. **Run the application**:
   ```bash
   npm start
   ```

6. **Access the app**:
   Open your browser and go to `http://localhost:3000`

## Usage Instructions

1. **Start Session**: Click "Start Session" to initialize the voice interface
2. **Talk to Rev**: Hold down the microphone button and speak
3. **Release to Send**: Release the button to send your voice message
4. **Interrupt**: Click "Interrupt" at any time to stop the AI and speak again
5. **End Session**: Click "End Session" when you're done

## Technical Implementation

### Architecture

```
┌─────────────────┐    WebSocket    ┌──────────────────┐    HTTP/REST    ┌─────────────────┐
│   Frontend      │ ◄─────────────► │   Node.js        │ ◄─────────────► │  Gemini Live    │
│   (Browser)     │                 │   Server         │                 │  API            │
└─────────────────┘                 └──────────────────┘                 └─────────────────┘
```

### Key Components

- **Frontend** (`public/index.html`): Web-based voice interface with WebSocket communication
- **Backend** (`server.js`): Express server with WebSocket handling and Gemini API integration
- **Gemini Integration** (`geminiLive.js`): Enhanced wrapper for Gemini Live API
- **System Instructions**: Customized prompts for Revolt Motors context

### API Models

For development and testing:
- `gemini-2.0-flash-live-001` (recommended for development)
- `gemini-live-2.5-flash-preview` (alternative for testing)

For production:
- `gemini-2.5-flash-preview-native-audio-dialog` (native audio, has rate limits)

## System Instructions

The AI assistant is configured with comprehensive knowledge about Revolt Motors:

- Company background and founding
- Product lineup (RV300, RV400)
- Technical specifications
- Pricing information
- Key features and benefits
- Sustainable transportation focus

## Performance Optimizations

- **Low Latency**: Optimized for 1-2 second response times
- **Efficient Audio Processing**: WebM audio format with Opus codec
- **Connection Management**: Proper WebSocket lifecycle handling
- **Error Handling**: Comprehensive error recovery and user feedback

## Troubleshooting

### Common Issues

1. **"Microphone access denied"**
   - Check browser permissions for microphone access
   - Ensure you're using HTTPS in production

2. **"Connection error"**
   - Verify your API key is correct
   - Check rate limits (especially with native audio model)
   - Ensure stable internet connection

3. **High latency**
   - Switch to `gemini-2.0-flash-live-001` for faster responses
   - Check your network connection
   - Verify server performance

### Development Tips

1. **Testing Different Models**:
   Edit `server.js` line with the model name:
   ```javascript
   model: 'gemini-2.0-flash-live-001' // Change this
   ```

2. **Debugging WebSocket**:
   Check browser console for WebSocket messages and errors

3. **Rate Limits**:
   The native audio model has strict rate limits on free tier. Use alternative models for extensive testing.

## Project Structure

```
revolt-voice-chat/
├── server.js              # Main server file
├── package.json           # Dependencies and scripts
├── geminiLive.js          # Gemini API integration
├── .env.example           # Environment variables template
├── README.md              # This file
└── public/
    └── index.html         # Frontend interface
```

## Deployment

### Local Development
```bash
npm run dev  # Uses nodemon for auto-restart
```

### Production
```bash
npm start    # Standard production start
```

### Environment Variables for Production
```
GEMINI_API_KEY=your_production_api_key
PORT=3000
NODE_ENV=production
```

## Demo Video Requirements

Your demo video should show:
1. Natural conversation with the AI about Revolt Motors
2. Clear interruption of the AI mid-response
3. Overall responsiveness and low latency
4. Different types of questions (products, specifications, pricing)

## API Reference

### WebSocket Messages

#### Client to Server
```javascript
// Start voice session
{ "type": "start_session" }

// Send audio data
{ "type": "audio_data", "audio": "base64_audio_data" }

// Interrupt AI
{ "type": "interrupt" }

// End session
{ "type": "end_session" }
```

#### Server to Client
```javascript
// Session started
{ "type": "session_started", "message": "Voice session started" }

// Audio response
{ "type": "audio_response", "audio": "base64_audio", "mimeType": "audio/wav" }

// Session interrupted
{ "type": "interrupted", "message": "AI interrupted successfully" }

// Error occurred
{ "type": "error", "message": "Error description" }
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Check the troubleshooting section
- Review Gemini Live API documentation
- Open an issue in the repository

---

**Note**: This implementation prioritizes functionality and performance over visual replication. The focus is on delivering a robust, low-latency voice interface that matches the conversational capabilities of the original Revolt Motors voice assistant.