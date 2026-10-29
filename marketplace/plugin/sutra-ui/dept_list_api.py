"""dept_list_api.py -- GET /api/native/_departments and POST /api/native/{root}/departments (PRD amendment A5, A5.3.6).

A stub from P1: the router is empty and app.py includes it before website_api, so `_departments` shadows no ref. P3 fills it."""
from fastapi import APIRouter

router = APIRouter()
