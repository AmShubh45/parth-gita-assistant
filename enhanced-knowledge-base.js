const fs = require('fs').promises;
const path = require('path');
const { GoogleGenerativeAI } = require('@google/generative-ai');

class EnhancedKrishnaKnowledgeBase {
    constructor(geminiApiKey) {
        this.verses = [];
        this.contextKeywords = {};
        this.versesWithEmbeddings = [];
        this.genAI = new GoogleGenerativeAI(geminiApiKey);
        this.embeddingModel = this.genAI.getGenerativeModel({ model: "embedding-001" });
        this.isInitialized = false;
    }

    async initialize() {
        try {
            console.log('🔄 Initializing Krishna Knowledge Base...');
            
            // Load verses from JSON file
            await this.loadVersesFromFile();
            
            // Generate embeddings for all verses
            await this.generateEmbeddings();
            
            this.isInitialized = true;
            console.log('✅ Krishna Knowledge Base initialized with semantic search');
            
        } catch (error) {
            console.error('❌ Error initializing knowledge base:', error);
            throw error;
        }
    }

    async loadVersesFromFile() {
        try {
            const filePath = path.join(__dirname, 'krishna-knowledge-base.json');
            const data = await fs.readFile(filePath, 'utf8');
            const jsonData = JSON.parse(data);
            
            this.verses = jsonData.verses;
            this.contextKeywords = jsonData.context_keywords;
            
            console.log(`📿 Loaded ${this.verses.length} verses from knowledge base`);
            
        } catch (error) {
            console.error('Error loading verses from file:', error);
            // Fallback to hardcoded verses if file not found
            await this.initializeFallbackVerses();
        }
    }

    async initializeFallbackVerses() {
        console.log('📋 Using fallback verses...');
        // Minimal fallback verses
        this.verses = [
            {
                id: 'bg_2_47',
                chapter: 2,
                verse: 47,
                sanskrit: 'कर्मण्येवाधिकारस्ते मा फलेषु कदाचन। मा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि॥',
                hindi: 'तुम्हारा अधिकार केवल कर्म करने में है, फल में कभी नहीं। तुम कर्मफल के हेतु मत बनो और न ही तुम्हारी अकर्म में आसक्ति हो।',
                meaning: 'यह निष्काम कर्म का मूल सिद्धांत है। फल की चिंता छोड़कर पूरी निष्ठा से काम करना ही सच्चा कर्मयोग है।',
                context_tags: ['कर्म', 'निष्काम', 'फल', 'कर्मयोग', 'कर्तव्य'],
                emotional_context: ['चिंता', 'तनाव', 'प्रेशर'],
                themes: ['detachment', 'duty', 'action']
            }
        ];
        
        this.contextKeywords = {
            'काम': ['कार्य', 'नौकरी', 'व्यापार', 'करियर'],
            'मन': ['चिंता', 'डर', 'गुस्सा', 'दुख']
        };
    }

    async generateEmbeddings() {
        console.log('🧠 Generating embeddings for semantic search...');
        
        this.versesWithEmbeddings = [];
        
        for (let i = 0; i < this.verses.length; i++) {
            const verse = this.verses[i];
            
            try {
                // Create comprehensive text for embedding
                const embeddingText = this.createEmbeddingText(verse);
                
                // Generate embedding using Gemini
                const result = await this.embeddingModel.embedContent(embeddingText);
                const embedding = result.embedding.values;
                
                this.versesWithEmbeddings.push({
                    ...verse,
                    embedding: embedding,
                    embeddingText: embeddingText
                });
                
                console.log(`📊 Generated embedding for verse ${verse.id} (${i + 1}/${this.verses.length})`);
                
                // Add small delay to avoid rate limiting
                await new Promise(resolve => setTimeout(resolve, 100));
                
            } catch (error) {
                console.error(`Error generating embedding for verse ${verse.id}:`, error);
                // Add verse without embedding as fallback
                this.versesWithEmbeddings.push({
                    ...verse,
                    embedding: null
                });
            }
        }
    }

    createEmbeddingText(verse) {
        // Combine all relevant text fields for better semantic understanding
        const textParts = [
            verse.hindi,
            verse.meaning,
            verse.detailed_explanation || '',
            verse.context_tags?.join(' ') || '',
            verse.emotional_context?.join(' ') || '',
            verse.themes?.join(' ') || '',
            verse.life_situations?.join(' ') || ''
        ].filter(Boolean);
        
        return textParts.join(' ');
    }

    async findRelevantVerses(query, maxResults = 3) {
        if (!this.isInitialized) {
            console.warn('Knowledge base not initialized, using fallback search');
            return this.fallbackSearch(query, maxResults);
        }

        try {
            // Generate embedding for the query
            const result = await this.embeddingModel.embedContent(query);
            const queryEmbedding = result.embedding.values;
            
            // Calculate similarities
            const similarities = [];
            
            for (const verse of this.versesWithEmbeddings) {
                if (verse.embedding) {
                    const similarity = this.cosineSimilarity(queryEmbedding, verse.embedding);
                    similarities.push({ verse, similarity });
                } else {
                    // Fallback to keyword matching for verses without embeddings
                    const keywordScore = this.calculateKeywordScore(query, verse);
                    similarities.push({ verse, similarity: keywordScore });
                }
            }
            
            // Sort by similarity and return top results
            const sortedResults = similarities
                .sort((a, b) => b.similarity - a.similarity)
                .slice(0, maxResults)
                .map(item => item.verse);
            
            console.log(`🎯 Found ${sortedResults.length} relevant verses for query: "${query}"`);
            
            return sortedResults;
            
        } catch (error) {
            console.error('Error in semantic search:', error);
            return this.fallbackSearch(query, maxResults);
        }
    }

    cosineSimilarity(vecA, vecB) {
        if (vecA.length !== vecB.length) {
            return 0;
        }
        
        let dotProduct = 0;
        let normA = 0;
        let normB = 0;
        
        for (let i = 0; i < vecA.length; i++) {
            dotProduct += vecA[i] * vecB[i];
            normA += vecA[i] * vecA[i];
            normB += vecB[i] * vecB[i];
        }
        
        if (normA === 0 || normB === 0) {
            return 0;
        }
        
        return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    fallbackSearch(query, maxResults) {
        const queryLower = query.toLowerCase();
        const queryWords = queryLower.split(/\s+/);
        
        const scores = this.verses.map(verse => {
            let score = 0;
            
            // Check context keywords
            for (const word of queryWords) {
                if (verse.context_tags && verse.context_tags.some(ctx => ctx.includes(word))) score += 3;
                if (verse.emotional_context && verse.emotional_context.some(ctx => ctx.includes(word))) score += 4;
                if (verse.hindi && verse.hindi.toLowerCase().includes(word)) score += 2;
                if (verse.meaning && verse.meaning.toLowerCase().includes(word)) score += 2;
            }
            
            // Check categorical matches
            for (const [category, keywords] of Object.entries(this.contextKeywords)) {
                if (keywords.some(keyword => queryLower.includes(keyword))) {
                    if (verse.context_tags && verse.context_tags.includes(category)) score += 5;
                }
            }
            
            return { verse, score };
        });

        return scores
            .filter(item => item.score > 0)
            .sort((a, b) => b.score - a.score)
            .slice(0, maxResults)
            .map(item => item.verse);
    }

    calculateKeywordScore(query, verse) {
        const queryLower = query.toLowerCase();
        const queryWords = queryLower.split(/\s+/);
        let score = 0;
        
        for (const word of queryWords) {
            if (verse.hindi && verse.hindi.toLowerCase().includes(word)) score += 2;
            if (verse.meaning && verse.meaning.toLowerCase().includes(word)) score += 2;
            if (verse.context_tags && verse.context_tags.some(tag => tag.includes(word))) score += 1;
            if (verse.emotional_context && verse.emotional_context.some(ctx => ctx.includes(word))) score += 1;
        }
        
        return score / 100; // Normalize to 0-1 range similar to cosine similarity
    }

    getRandomVerse() {
        if (this.verses.length === 0) return null;
        return this.verses[Math.floor(Math.random() * this.verses.length)];
    }

    getVersesByChapter(chapter) {
        return this.verses.filter(v => v.chapter == chapter);
    }

    getVerseById(id) {
        return this.verses.find(v => v.id === id);
    }

    // Get statistics about the knowledge base
    getStats() {
        return {
            totalVerses: this.verses.length,
            versesWithEmbeddings: this.versesWithEmbeddings.filter(v => v.embedding).length,
            categories: Object.keys(this.contextKeywords).length,
            chapters: [...new Set(this.verses.map(v => v.chapter))].length,
            isInitialized: this.isInitialized
        };
    }

    // Search verses by multiple criteria
    async advancedSearch(options = {}) {
        const {
            query = '',
            chapter = null,
            themes = [],
            emotional_context = [],
            life_situations = [],
            maxResults = 5
        } = options;

        let results = this.verses;

        // Filter by chapter if specified
        if (chapter !== null) {
            results = results.filter(v => v.chapter === chapter);
        }

        // Filter by themes
        if (themes.length > 0) {
            results = results.filter(v => 
                v.themes && themes.some(theme => v.themes.includes(theme))
            );
        }

        // Filter by emotional context
        if (emotional_context.length > 0) {
            results = results.filter(v => 
                v.emotional_context && emotional_context.some(emotion => 
                    v.emotional_context.includes(emotion)
                )
            );
        }

        // Filter by life situations
        if (life_situations.length > 0) {
            results = results.filter(v => 
                v.life_situations && life_situations.some(situation => 
                    v.life_situations.includes(situation)
                )
            );
        }

        // If query is provided, use semantic search on filtered results
        if (query.trim()) {
            const tempKB = Object.create(this);
            tempKB.verses = results;
            tempKB.versesWithEmbeddings = this.versesWithEmbeddings.filter(v => 
                results.some(r => r.id === v.id)
            );
            
            return await tempKB.findRelevantVerses(query, maxResults);
        }

        // Return filtered results, limited by maxResults
        return results.slice(0, maxResults);
    }

    // Save updated knowledge base back to file
    async saveToFile() {
        try {
            const filePath = path.join(__dirname, 'krishna-knowledge-base.json');
            const dataToSave = {
                verses: this.verses,
                context_keywords: this.contextKeywords
            };
            
            await fs.writeFile(filePath, JSON.stringify(dataToSave, null, 2));
            console.log('✅ Knowledge base saved to file');
            
        } catch (error) {
            console.error('Error saving knowledge base:', error);
            throw error;
        }
    }

    // Add a new verse to the knowledge base
    async addVerse(verseData) {
        try {
            // Validate required fields
            const requiredFields = ['id', 'chapter', 'verse', 'sanskrit', 'hindi', 'meaning'];
            for (const field of requiredFields) {
                if (!verseData[field]) {
                    throw new Error(`Missing required field: ${field}`);
                }
            }

            // Check if verse already exists
            if (this.verses.find(v => v.id === verseData.id)) {
                throw new Error(`Verse with ID ${verseData.id} already exists`);
            }

            // Add to verses array
            this.verses.push(verseData);

            // Generate embedding if initialized
            if (this.isInitialized) {
                const embeddingText = this.createEmbeddingText(verseData);
                const result = await this.embeddingModel.embedContent(embeddingText);
                const embedding = result.embedding.values;

                this.versesWithEmbeddings.push({
                    ...verseData,
                    embedding: embedding,
                    embeddingText: embeddingText
                });
            }

            console.log(`✅ Added new verse: ${verseData.id}`);
            
        } catch (error) {
            console.error('Error adding verse:', error);
            throw error;
        }
    }
}

module.exports = EnhancedKrishnaKnowledgeBase;