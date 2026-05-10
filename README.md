# SafeLink Safety Chatbot

A comprehensive disaster relief chatbot module for the SafeLink app. Provides accurate, actionable disaster-safety guidance with offline-first support, focused on **Earthquake** and **Flood** disasters.

## Features

### Backend (Python/FastAPI)
- **NLP Pipeline**: Intent classification, entity extraction, knowledge retrieval
- **Disaster Safety Guidance**: Earthquake and Flood coverage
- **Emergency Detection**: Quick routing of emergency situations
- **Helpline Database**: Emergency contacts (Rescue 1122, Edhi, NDMA, etc.)
- **First Aid Information**: Basic first aid guidance with appropriate disclaimers
- **Offline Support**: Cacheable data for offline-first operation
- **Privacy-First**: PII detection and anonymization

### Frontend (Flutter)
- **Chat Interface**: Modern, responsive chat UI
- **Offline Mode**: Works without internet using cached data
- **Quick Dial**: One-tap emergency calling
- **Smart Suggestions**: Context-aware action suggestions

## Supported Disasters

| Disaster | Coverage |
|----------|----------|
| 🏚️ Earthquake | Full (Before, During, After) |
| 🌊 Flood | Full (Before, During, After) |

## Emergency Contacts

| Service | Number |
|---------|---------|
| Rescue 1122 | 1122 |
| Edhi Foundation | 115 |
| Police | 15 |
| Fire Brigade | 16 |
| NDMA | 051-9205037 |
| Flood Forecasting | 042-99200296 |

## Quick Start

### Backend Setup

1. **Navigate to the chatbot server directory:**
   ```bash
   cd chatbot_server
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment (optional):**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Run the server:**
   ```bash
   # Development
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   
   # Or using Python
   python -m chatbot_server.main
   ```

6. **Access the API:**
   - API Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc
   - Health Check: http://localhost:8000/health

### Flutter Setup

1. **Add dependencies to pubspec.yaml** (already added):
   ```yaml
   dependencies:
     http: ^1.2.0
     url_launcher: ^6.2.2
   ```

2. **Run flutter pub get:**
   ```bash
   flutter pub get
   ```

3. **Update the API URL** in `lib/features/chatbot/services/chatbot_service.dart`:
   ```dart
   // For Android Emulator
   static const String _baseUrl = 'http://10.0.2.2:8000/api/v1';
   
   // For iOS Simulator
   static const String _baseUrl = 'http://localhost:8000/api/v1';
   
   // For Production
   static const String _baseUrl = 'https://your-server.com/api/v1';
   ```

4. **Navigate to the chatbot:**
   ```dart
   Get.toNamed(AppRoutes.chatView);
   ```

## API Endpoints

### Chat
- `POST /api/v1/chat/message` - Send a message to the chatbot
- `POST /api/v1/chat/feedback` - Submit feedback on a response
- `GET /api/v1/chat/helplines/{region}` - Get helplines for a region
- `GET /api/v1/chat/offline-data` - Get offline data package
- `GET /api/v1/chat/quick-tip/{disaster_type}` - Get quick safety tip

### Health
- `GET /health` - Health check
- `GET /ready` - Readiness check (for k8s)

## Architecture

```
chatbot_server/
├── main.py                 # FastAPI app entry point
├── config.py               # Configuration & settings
├── models/
│   └── schemas.py          # Pydantic models
├── nlp/
│   ├── preprocessor.py     # Text normalization & PII handling
│   ├── intent_classifier.py # Intent classification
│   ├── entity_extractor.py  # Entity extraction
│   └── knowledge_retriever.py # Knowledge base retrieval
├── services/
│   └── chatbot_service.py  # Main chatbot orchestration
├── routers/
│   └── chat_router.py      # API endpoints
└── data/
    ├── helplines.json      # Emergency contacts database
    └── response_templates.json # Response templates

lib/features/chatbot/
├── models/
│   └── chat_models.dart    # Data models
├── services/
│   └── chatbot_service.dart # API & offline service
├── controllers/
│   └── chat_controller.dart # State management
└── presentation/
    ├── screens/
    │   └── chat_view.dart  # Main chat screen
    └── widgets/
        ├── chat_bubble.dart # Message bubble
        └── chat_input_field.dart # Input field
```

## Intent Types

| Intent | Description |
|--------|-------------|
| `safety_advice` | Disaster safety guidance requests |
| `helpline_query` | Emergency number queries |
| `shelter_info` | Evacuation/shelter information |
| `first_aid` | Medical/first aid questions |
| `weather_info` | Weather-related queries |
| `report_incident` | Incident reporting |
| `emergency` | Emergency situations |
| `greetings` | Hello/hi messages |
| `farewell` | Goodbye messages |
| `gratitude` | Thank you messages |
| `fallback` | Unrecognized queries |

## Supported Disaster Types

- **Earthquake** — Full coverage (Before, During, After)
- **Flood** — Full coverage (Before, During, After)

## Coverage

- All provinces and territories supported
- Extensible for additional regions

## Safety Considerations

1. **Emergency Escalation**: Emergency keywords immediately trigger emergency response with helpline numbers
2. **Medical Disclaimers**: First aid information includes appropriate medical disclaimers
3. **No Medical Diagnosis**: The bot never provides medical diagnoses
4. **No Legal Advice**: The bot never provides legal advice
5. **Verified Content**: All guidance is from verified sources (NDMA, FEMA, WHO, CDC, Red Cross)
6. **Confidence Thresholds**: Low-confidence responses include warnings

## Extending the Knowledge Base

1. **Add new disaster guidance:**
   Edit `chatbot_server/nlp/knowledge_retriever.py` or create `data/knowledge_base.json`

2. **Add new helplines:**
   Edit `chatbot_server/data/helplines.json`

3. **Add new response templates:**
   Edit `chatbot_server/data/response_templates.json`

## Production Deployment

### Docker
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY chatbot_server/ .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables
See `.env.example` for all configuration options.

## Testing

```bash
# Run tests
pytest

# Test API manually
curl -X POST http://localhost:8000/api/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "What should I do during an earthquake?", "region": "default"}'
```

## License

This module is part of the SafeLink disaster relief application.

## Disclaimer

This chatbot provides general safety information and should not replace official emergency services. For life-threatening emergencies, always call your local emergency number directly:

- **Rescue 1122**
- **Edhi Foundation**: 115
- **Police**: 15
