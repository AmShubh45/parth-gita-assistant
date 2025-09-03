# पार्थ - Gita Assistant 🕉️

[![Node.js](https://img.shields.io/badge/Node.js-v18+-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Gemini AI](https://img.shields.io/badge/Gemini-AI-4285f4?logo=google&logoColor=white)](https://ai.google.dev/)
[![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-orange)](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)

An AI-powered voice assistant that embodies the wisdom of Lord Krishna from the Bhagavad Gita. Paarth provides spiritual guidance and practical life solutions through an immersive voice interface, combining ancient Sanskrit wisdom with modern AI technology.

## ✨ Features

### 🎙️ Advanced Voice Interface
- **Real-time speech recognition** with optimized audio processing
- **Natural Hindi TTS** with Krishna's divine persona
- **Push-to-talk** and **continuous listening** modes
- **Audio visualization** during conversation

### 🧠 Semantic Knowledge Base
- **RAG (Retrieval-Augmented Generation)** with Gemini embeddings
- **100+ Bhagavad Gita verses** with contextual understanding
- **Semantic search** for relevant verse retrieval
- **Multi-context matching** (emotional, situational, thematic)

### 📿 Spiritual Intelligence
- **Krishna persona** with authentic spiritual guidance
- **Contextual verse selection** based on user queries
- **Life situation mapping** to Gita teachings
- **Practical solutions** grounded in dharmic principles

### 🌐 Real-time Architecture
- **WebSocket-based** instant communication
- **Session management** with conversation history
- **Concurrent user support** with individual contexts
- **Auto-cleanup** of inactive sessions

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ 
- Google Gemini API key
- Modern web browser with microphone access

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/parth-gita-assistant.git
cd parth-gita-assistant

# Install dependencies
npm install

# Set up environment variables
cp .env.example .env
# Add your GEMINI_API_KEY to .env

# Initialize the knowledge base
npm run setup

# Start the server
npm start
```

### Environment Setup

Create a `.env` file with:

```env
GEMINI_API_KEY=your_gemini_api_key_here
NODE_ENV=development
PORT=8080
```

### Access the Assistant

1. Open your browser to `http://localhost:8080`
2. Allow microphone permissions when prompted
3. Click the microphone button and ask your spiritual questions in Hindi or English
4. Listen to Krishna's wisdom and guidance

## 📊 Knowledge Base Architecture

### Enhanced RAG System

```
User Query → Audio/Text Processing → Semantic Search → Verse Retrieval → Context Integration → Krishna Response
```

#### Semantic Search Features
- **Embedding-based similarity** using Gemini's embedding model
- **Multi-dimensional context matching**:
  - Emotional states (चिंता, डर, गुस्सा, etc.)
  - Life situations (career, relationships, health)
  - Spiritual themes (karma, dharma, devotion)
  - Sanskrit concept mapping

#### Knowledge Base Structure
```json
{
  "verses": [
    {
      "id": "bg_2_47",
      "chapter": 2,
      "verse": 47,
      "sanskrit": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।",
      "hindi": "तुम्हारा अधिकार केवल कर्म करने में है...",
      "meaning": "Practical explanation in modern context",
      "context_tags": ["कर्म", "निष्काम", "कर्तव्य"],
      "emotional_context": ["चिंता", "तनाव", "प्रेशर"],
      "life_situations": ["work", "career", "duty"],
      "themes": ["detachment", "action", "responsibility"]
    }
  ]
}
```

## 🏗️ System Architecture

### Core Components

#### 1. Enhanced Knowledge Base (`enhanced-knowledge-base.js`)
- Semantic verse search with embeddings
- Context-aware retrieval system
- Multi-criteria advanced search
- Dynamic knowledge base updates

#### 2. Krishna Speech Processor
- Audio transcription using Gemini
- Contextual response generation
- Session-aware conversation management
- Multi-modal input processing

#### 3. Session Management
- Real-time WebSocket connections
- User conversation history
- Devotional progress tracking
- Auto-cleanup mechanisms

#### 4. Web Interface (`index.html`)
- Responsive spiritual UI design
- Real-time audio processing
- Visual feedback systems
- Accessibility features

### API Architecture

#### WebSocket Events
```javascript
// Audio input
{
  "type": "audio_data",
  "audio": "base64_audio_data",
  "context": "krishna_conversation"
}

// Text query
{
  "type": "text_query", 
  "query": "जीवन में कर्म का क्या महत्व है?"
}

// Krishna's response
{
  "type": "text_response",
  "text": "वत्स, कर्म ही जीवन का आधार है...",
  "versesUsed": ["bg_2_47", "bg_3_8"],
  "processingTime": 1250
}
```

#### REST Endpoints
```
GET  /health                     - System health check
GET  /api/krishna/verses         - Browse verses
POST /api/krishna/search         - Semantic verse search
POST /api/krishna/advanced-search - Multi-criteria search
POST /api/krishna/ask           - Direct text queries
GET  /api/krishna/stats         - Knowledge base analytics
```

## 🔧 Configuration

### Knowledge Base Customization

Add new verses to `krishna-knowledge-base.json`:

```javascript
await knowledgeBase.addVerse({
  id: "bg_custom_1",
  chapter: 18,
  verse: 66,
  sanskrit: "सर्वधर्मान्परित्यज्य मामेकं शरणं व्रज।",
  hindi: "सभी धर्मों को छोड़कर मेरी शरण में आओ।",
  meaning: "Complete surrender leads to liberation...",
  context_tags: ["समर्पण", "मोक्ष", "शरण"],
  emotional_context: ["निराशा", "खोज", "शांति"],
  themes: ["surrender", "liberation", "devotion"]
});
```

### Advanced Search Configuration

```javascript
const searchResults = await knowledgeBase.advancedSearch({
  query: "कर्म योग क्या है?",
  chapter: 3,
  themes: ["action", "duty"],
  emotional_context: ["confusion", "doubt"],
  maxResults: 5
});
```

## 🚁 Deployment

### Fly.io Deployment

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login to Fly.io
fly auth login

# Deploy the application
fly launch

# Set environment variables
fly secrets set GEMINI_API_KEY=your_api_key

# Deploy updates
fly deploy
```

### Docker Deployment

```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 8080
CMD ["node", "server.js"]
```

### Environment Variables for Production

```env
NODE_ENV=production
GEMINI_API_KEY=your_production_api_key
PORT=8080
LOG_LEVEL=info
EMBEDDING_BATCH_SIZE=10
MAX_SESSIONS=1000
```

## 📈 Performance Optimization

### Knowledge Base Performance
- **Embedding caching** for faster similarity search
- **Batch processing** for large verse collections  
- **Memory-efficient** vector operations
- **Lazy loading** of embeddings

### WebSocket Optimization
- **Connection pooling** with automatic cleanup
- **Message compression** for large responses
- **Rate limiting** to prevent abuse
- **Heartbeat monitoring** for connection health

### Audio Processing
- **Optimized codecs** (WebM/Opus) for quality
- **Adaptive bitrate** based on connection
- **Echo cancellation** and noise suppression
- **Low-latency** audio pipelines

## 🧪 Testing

### Run Tests

```bash
# Unit tests
npm test

# Integration tests  
npm run test:integration

# Load testing
npm run test:load

# Knowledge base validation
npm run validate:kb
```

### Test the Knowledge Base

```javascript
// Test semantic search
const results = await knowledgeBase.findRelevantVerses(
  "मुझे जीवन में शांति नहीं मिल रही", 
  3
);

console.log(`Found ${results.length} relevant verses`);
```

## 📚 Usage Examples

### Voice Interaction

```
User: "मेरे काम में बहुत तनाव है, क्या करूं?"

Krishna: "वत्स, गीता के अध्याय 2, श्लोक 47 में मैं कहता हूं - 
'कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।' 
तुम्हारा अधिकार केवल कर्म में है, फल में नहीं। 
फल की चिंता छोड़कर पूरी निष्ठा से काम करो।"
```

### API Usage

```javascript
// Direct API call
const response = await fetch('/api/krishna/ask', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    question: "धर्म और अधर्म में क्या अंतर है?"
  })
});

const guidance = await response.json();
console.log(guidance.response);
```

## 🤝 Contributing

We welcome contributions to enhance Paarth's spiritual intelligence!

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/yourusername/parth-gita-assistant.git
cd parth-gita-assistant

# Create feature branch
git checkout -b feature/enhance-knowledge-base

# Make your changes and test
npm run test

# Submit pull request
git push origin feature/enhance-knowledge-base
```

### Areas for Contribution
- **Additional verses** with contextual tags
- **Multilingual support** (Sanskrit, English, regional languages)
- **Advanced AI models** integration
- **Mobile app** development
- **Voice synthesis** improvements

## 📋 Roadmap

### Phase 1: Core Enhancement ✅
- [x] Semantic search with embeddings
- [x] Advanced RAG implementation
- [x] Real-time voice processing
- [x] Krishna persona development

### Phase 2: Intelligence Expansion 🚧
- [ ] Multi-language support (English, Sanskrit)
- [ ] Emotional intelligence enhancement  
- [ ] Personal spiritual progress tracking
- [ ] Advanced conversation memory

### Phase 3: Platform Extension 📅
- [ ] Mobile applications (iOS/Android)
- [ ] WhatsApp integration
- [ ] Telegram bot
- [ ] Desktop applications

### Phase 4: Community Features 📅
- [ ] User community platform
- [ ] Shared spiritual discussions
- [ ] Guided meditation sessions
- [ ] Daily wisdom notifications

## ⚠️ Limitations & Considerations

### Technical Limitations
- Requires stable internet connection for AI processing
- Audio quality dependent on device microphone
- Processing latency varies with server load
- Embedding generation requires significant computational resources

### Spiritual Context
- AI interpretation of ancient texts requires careful validation
- Responses are generated, not direct scriptural quotes
- Users should seek human spiritual guidance for complex life decisions
- Cultural context may vary across different traditions

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Sage Vyasa** for the eternal wisdom of Bhagavad Gita
- **Google Gemini AI** for advanced language processing
- **Open source community** for foundational technologies
- **Sanskrit scholars** for accurate translations and interpretations

## 📞 Support

For technical support or spiritual guidance:
- **Issues**: [GitHub Issues](https://github.com/AmShubh45/parth-gita-assistant/issues)
- **Discussions**: [GitHub Discussions](https://github.com/AmShubh45/parth-gita-assistant/discussions)
- **Email**: shubhampandey45.sp@gmail.com

---

*"यदा यदा हि धर्मस्य ग्लानिर्भवति भारत। अभ्युत्थानमधर्मस्य तदात्मानं सृजाम्यहम्।।"*

*"Whenever dharma declines and adharma rises, I manifest myself to restore righteousness."* - Bhagavad Gita 4.7

Built with 💛 for spiritual seekers worldwide
