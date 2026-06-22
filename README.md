# 🏋️ AI Fitness and Nutrition Planner

> **Personalized AI-powered fitness and nutrition planning** — Generate custom workout routines, meal plans, recipes, and track progress all in one place.

[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red?style=flat-square&logo=streamlit)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)](https://www.python.org)
[![Google AI](https://img.shields.io/badge/Google_AI-Gemini%20%2B%20Imagen-yellow?style=flat-square&logo=google)](https://ai.google.dev)
[![API](https://img.shields.io/badge/API-Spoonacular-green?style=flat-square)](https://spoonacular.com/food-api)


**[🚀 Live Demo](https://personalized-workout-and-diet-planner-with-ai-kk6tks7cpms7ppb9.streamlit.app/)** • **[Report Issue](https://github.com/SabarishR08/AI-Fitness-and-Nutrition-Planner/issues)**

---

## Problem & Solution

Traditional fitness apps often rely on static templates and generic plans that ignore what truly matters:

- Individual goals and current fitness level
- Dietary preferences or cultural food habits
- Allergies and restrictions
- Daily schedule and available time
- Budget limitations

This AI-powered planner uses Google Gemini and Spoonacular to tailor workouts, recipes, and nutrition plans to each user's exact requirements, ensuring every plan is practical, personalized, and achievable.

---

## Features

| Feature | Description |
|---------|-------------|
| Workout Plan Generation | 7-day personalized routines based on goals, fitness level, and BMI |
| Recipe Search | Real recipes via Spoonacular API with AI fallback; includes nutritional breakdown |
| Grocery List Generator | Aggregates and normalizes ingredients from recipes; exportable as CSV |
| Progress Tracking | Log weight daily and visualize trends with interactive charts |
| Motivational Content | Personalized quotes and AI-generated images |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Streamlit |
| AI/LLM | Google Gemini API |
| Image Generation | Google Imagen API |
| Recipe Data | Spoonacular API |
| Data Visualization | Plotly |
| Data Processing | Pandas, NumPy |
| Storage | Session-based (CSV export) |

---

## Project Structure

```
.
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── README.md                 # This file
└── data/
    └── user_logs.json        # User progress data
```
    
