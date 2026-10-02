# Quick Start: Manual Testing Guide

## Prerequisites

1. Verify Ollama is running: curl http://localhost:11434/api/tags
2. Verify model available: ollama list
3. Check test repository exists in backend/.pytest-tmp/

## Option 1: Automated Core Pipeline Test (5 minutes)

Test the LLM pipeline without starting servers:

cd backend
python test_e2e.py

Expected: 4 files, 4 functions, 4 LLM calls, 1 finding validated

## Option 2: Full UI Integration Test (15 minutes)

### Terminal 1 - Start Backend
cd backend
python -m uvicorn app.main:app --reload

### Terminal 2 - Start Frontend
cd frontend
npm run dev

### Browser Test
1. Open http://localhost:5173
2. Upload backend/.pytest-tmp/test_repo_*.zip
3. Wait 15-30 seconds for analysis
4. Go to Bug Management tab
5. Verify 1 semantic finding appears

## Option 3: API Testing

Requires backend running. Test endpoints:
- POST /api/v1/repositories/upload
- GET /api/v1/repositories/{id}/analysis-status
- GET /api/v1/repositories/{id}/candidate-issues

## Troubleshooting

- Ollama not responding: restart ollama serve
- Backend errors: pip install -r requirements.txt
- Frontend errors: npm install
- No findings: check backend logs for semantic_llm output

## Success Criteria

Option 1: Test passes, 4 LLM calls, 1 finding
Option 2: Finding visible in UI with evidence
Option 3: API returns 1 candidate issue

