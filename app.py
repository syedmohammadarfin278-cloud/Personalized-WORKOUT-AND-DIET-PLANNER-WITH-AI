import streamlit as st
import requests
import json
import time
import math
from datetime import datetime, date
import pandas as pd
import plotly.express as px
import re 
from collections import Counter 
import os
from dotenv import load_dotenv

# --- 1. CONFIGURATION AND API SETUP ---

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")

# API Endpoints
GEMINI_MODEL = "gemini-2.5-flash"
IMAGE_MODEL = "imagen-3.0-generate-002"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
IMAGE_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGE_MODEL}:predict?key={GEMINI_API_KEY}"
SPOONACULAR_SEARCH_URL = "https://api.spoonacular.com/recipes/complexSearch"

# User explicitly set this to False
OFFLINE_MOCK_MODE = False


# --- 2. UTILITY FUNCTIONS (API/MATH/MOCK) ---

def exponential_backoff_fetch(url, payload=None, max_retries=5):
    """Handles API requests with exponential backoff for resilience."""
    method = 'POST' if payload else 'GET'
    
    for attempt in range(max_retries):
        try:
            headers = {'Content-Type': 'application/json'}
            
            if method == 'POST':
                response = requests.post(url, headers=headers, json=payload)
            else:
                response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            
            # Non-4xx errors -> retry
            if 500 <= response.status_code < 600:
                raise requests.exceptions.RequestException(f"Server error {response.status_code}. Retrying...")

            # 4xx errors -> don't retry, break and return error
            if 400 <= response.status_code < 500:
                st.error(f"API Client Error {response.status_code}: {response.text}")
                return None
            
        except requests.exceptions.RequestException as e:
            st.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                st.error(f"Final fetch failed after {max_retries} attempts.")
                return None
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            return None
    return None

def calculate_bmi(weight_kg, height_cm):
    """Calculates Body Mass Index and returns tuple (bmi, category)."""
    if not weight_kg or not height_cm or height_cm == 0:
        return None, None
    try:
        height_m = height_cm / 100
        bmi = round(weight_kg / (height_m * height_m), 2)
        
        if bmi < 18.5:
            category = "Underweight"
        elif bmi < 24.9:
            category = "Normal Weight"
        elif bmi < 29.9:
            category = "Overweight"
        else:
            category = "Obesity"
        
        return bmi, category
    except Exception:
        return None, None

def get_bmi_style(category):
    """Returns markdown for colored BMI display."""
    color_map = {
        "Underweight": "lightblue", 
        "Normal Weight": "green", 
        "Overweight": "orange", 
        "Obesity": "red"
    }
    color = color_map.get(category, "gray")
    return f":{color}[**{category}**]"


def mock_gemini_response(prompt):
    """Provides structured mock responses for offline/error mode."""
    if "workout" in prompt.lower():
        return "## Personalized 7-Day Workout Plan (MOCK)\n\n| Day | Focus | Exercises (Sets x Reps) |\n|---|---|---|\n| 1 | Full Body A | Squats (3x10), Push-ups (3xMax) |\n| 2 | Active Rest | 30 min brisk walk |\n| 3 | Full Body B | Deadlifts (3x8), Overhead Press (3x10) |\n| 4 | Rest | Complete Rest |\n| 5 | Cardio/Core | 45 min Cycle, Plank (3x60s) |"
    if "meal" in prompt.lower():
        return "## Personalized 7-Day Meal Plan (MOCK)\n\n| Day | Breakfast | Lunch | Dinner |\n|---|---|---|---|\n| 1 | Oatmeal | Chicken Salad | Salmon w/ Veg |\n| 2 | Eggs & Toast | Turkey Sandwich | Lentil Soup |\n\n**Target Macros (Daily):** Protein: 150g, Fat: 60g, Carbs: 200g."
    if "motivational" in prompt.lower():
        return "The only bad workout is the one that didn't happen."
    if "recipe" in prompt.lower():
        return json.dumps([{
            "recipeName": "High-Protein Lentil & Spinach Curry (Mock)",
            "description": "A robust, flavorful, and filling vegetarian curry packed with protein and iron.",
            "ingredients": ["1 cup red lentils", "4 cups vegetable broth", "1 onion, chopped", "1 tbsp curry powder"],
            "instructionsSummary": "Sauté ingredients, simmer lentils, and stir in spinach and coconut milk.",
            "macrosGrams": {"protein": 35, "fat": 12, "carbs": 50},
            "fullInstructions": "Step 1: Sauté the aromatics. Step 2: Add lentils and broth and cook for 20 minutes. Step 3: Stir in remaining ingredients and serve."
        }])
    return "Mock response for an unspecified request."

def parse_spoonacular_recipe(recipe_data):
    """Extracts and standardizes macro and instruction data from Spoonacular result."""
    macros = {'protein': 0, 'fat': 0, 'carbs': 0}
    if 'nutrition' in recipe_data and 'nutrients' in recipe_data['nutrition']:
        for nutrient in recipe_data['nutrition']['nutrients']:
            name = (nutrient.get('title') or nutrient.get('name', '')).lower()
            amount = nutrient.get('amount', 0)
            if 'protein' in name: macros['protein'] = round(amount, 1)
            elif 'fat' in name: macros['fat'] = round(amount, 1)
            elif 'carbohydrates' in name or 'carbs' in name: macros['carbs'] = round(amount, 1)

    # FIX: Use re.sub to correctly remove HTML tags from summary
    summary = re.sub(r'<[^>]+>', '', recipe_data.get('summary', 'No summary available.')).strip()
    summary = summary[:150] + '...' if len(summary) > 150 else summary

    return {
        'recipeName': recipe_data.get('title', 'Untitled Recipe'),
        # NOTE: Keeping image URL in data structure just in case, but it won't be displayed in UI.
        'image': recipe_data.get('image'), 
        'description': summary,
        'ingredients': [i['original'] for i in recipe_data.get('extendedIngredients', [])],
        'instructionsSummary': "See full instructions below.",
        'macrosGrams': macros,
        'fullInstructions': recipe_data.get('instructions', 'No full instructions provided.')
    }

# --- 3. CORE API CALLS ---

def generate_plan(prompt, system_instruction, key):
    """Generates text content (plans/messages) using Gemini."""
    if OFFLINE_MOCK_MODE or not GEMINI_API_KEY:
        st.session_state[key] = mock_gemini_response(prompt)
        return

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
    }
    
    with st.spinner(f"Generating your personalized {key} plan..."):
        response_data = exponential_backoff_fetch(GEMINI_API_URL, payload)

    # FIX: Robust check for response data structure
    if response_data and response_data.get('candidates') and response_data['candidates'][0].get('content'):
        text = response_data['candidates'][0]['content']['parts'][0]['text']
        st.success(f"Successfully generated {key} plan!")
    else:
        st.error(f"Failed to parse Gemini response for {key}. Using mock data as fallback.")
        text = mock_gemini_response(prompt)

    st.session_state[key] = text

def find_recipes(query, macro_targets):
    """Searches Spoonacular, falling back to Gemini structured JSON."""
    st.session_state.generated_recipes = []
    st.session_state.recipe_source = ""
    
    # 1. Try Spoonacular
    if SPOONACULAR_API_KEY and not OFFLINE_MOCK_MODE:
        try:
            params = {
                "query": query,
                "number": 3,
                "apiKey": SPOONACULAR_API_KEY,
                "addRecipeInformation": True,
                "addRecipeNutrition": True
            }
            with st.spinner("Searching Spoonacular for recipes..."):
                search_response = requests.get(SPOONACULAR_SEARCH_URL, params=params).json()

            if search_response.get('results') and len(search_response['results']) > 0:
                recipes = [parse_spoonacular_recipe(r) for r in search_response['results']]
                st.session_state.generated_recipes = recipes
                st.session_state.recipe_source = "Spoonacular"
                st.success(f"Found {len(recipes)} recipes via Spoonacular!")
                return

        except Exception as e:
            st.warning(f"Spoonacular failed, falling back to Gemini. Error: {e}")

    # 2. Fallback to Gemini Structured JSON
    if GEMINI_API_KEY and not OFFLINE_MOCK_MODE:
        try:
            recipe_prompt = f"Generate 3 unique recipes for '{query}' aiming for macros: Protein {macro_targets['Protein']}g, Fat {macro_targets['Fat']}g, Carbs {macro_targets['Carbs']}g."
            
            payload = {
                "contents": [{"parts": [{"text": recipe_prompt}]}],
                "systemInstruction": {"parts": [{"text": "You are an expert chef. Generate 3 unique recipes in a strict JSON array format adhering to the schema. Do not output any text outside of the JSON array."}]},
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "recipeName": {"type": "STRING"},
                                "description": {"type": "STRING"},
                                "ingredients": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "instructionsSummary": {"type": "STRING"},
                                "macrosGrams": {"type": "OBJECT", "properties": {"protein": {"type": "NUMBER"}, "fat": {"type": "NUMBER"}, "carbs": {"type": "NUMBER"}}},
                                "fullInstructions": {"type": "STRING"}
                            }
                        }
                    }
                }
            }

            with st.spinner("Generating structured recipes with Gemini AI..."):
                response_data = exponential_backoff_fetch(GEMINI_API_URL, payload)

            # FIX: Robust check for response data structure
            if response_data and response_data.get('candidates') and response_data['candidates'][0].get('content'):
                json_text = response_data['candidates'][0]['content']['parts'][0]['text']
                recipes = json.loads(json_text)
                st.session_state.generated_recipes = recipes
                st.session_state.recipe_source = "Gemini AI"
                st.success(f"Found {len(recipes)} recipes via Gemini AI!")
                return
            else:
                raise Exception("Gemini returned empty or malformed structured response.")
            
        except Exception as e:
            st.error(f"Gemini structured generation failed: {e}. Falling back to mock data.")

    # 3. Final Mock Fallback
    st.session_state.generated_recipes = json.loads(mock_gemini_response("recipe"))
    st.session_state.recipe_source = "Mock Data"
    st.info("Using mock recipes.")


def generate_image(prompt):
    """Generates an image using the Imagen API."""
    
    # FIX: Use a fallback image URL if API key is missing
    fallback_url = "https://placehold.co/800x400/36A3F4/ffffff?text=MOTIVATION+IS+MOCKED"
    if OFFLINE_MOCK_MODE or not GEMINI_API_KEY:
        st.session_state.motivation_image_url = fallback_url
        st.error("Image generation skipped: API key missing or in mock mode.")
        return
    
    try:
        image_prompt = f"Highly motivational poster background, ultra-wide cinematic shot, featuring the text '{prompt}' overlay, athletic style, epic feel, high resolution, soft focus."
        payload = {
            "instances": [{"prompt": image_prompt}],
            "parameters": {"sampleCount": 1}
        }
        
        with st.spinner("Creating your motivational image..."):
            response_data = exponential_backoff_fetch(IMAGE_API_URL, payload)

        if response_data and response_data.get('predictions'):
            base64_data = response_data['predictions'][0]['bytesBase64Encoded']
            st.session_state.motivation_image_url = f"data:image/png;base64,{base64_data}"
            st.success("Motivational image created!")
        else:
            raise Exception("No image prediction returned.")

    except Exception as e:
        st.error(f"Image generation failed: {e}")
        st.session_state.motivation_image_url = fallback_url


# --- 4. STATE INITIALIZATION ---

def init_state():
    """Initializes Streamlit session state variables."""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        # Profile Inputs
        st.session_state.user_name = "Fitness Fan"
        st.session_state.user_weight = 75.0
        st.session_state.user_height = 175.0
        st.session_state.user_goals = "Build 5kg of lean muscle."
        st.session_state.user_level = "Intermediate"
        st.session_state.user_diet = "Standard"
        st.session_state.user_time = "1 hour"
        st.session_state.macro_protein = 150
        st.session_state.macro_fat = 60
        st.session_state.macro_carbs = 200
        # Output Variables
        st.session_state.workout_plan = ""
        st.session_state.diet_plan = ""
        st.session_state.generated_recipes = []
        st.session_state.recipe_source = ""
        st.session_state.motivation_message = ""
        st.session_state.motivation_image_url = ""
        # Progress Tracker (Simulated Persistence)
        st.session_state.weight_logs = []
        st.session_state.log_weight = st.session_state.user_weight
        st.session_state.log_date = date.today()
        st.session_state.log_error = False
        st.session_state.delete_log_select = "-- Select a log --" # Initialized key for selectbox

# --- 5. UI COMPONENTS (RENDERERS) ---

def render_sidebar():
    """Renders the user profile and input parameters in the sidebar."""
    st.sidebar.title("👤 Your Profile & Goals")

    # FIX: Giving text_input a unique key ('user_name_input') to resolve Streamlit warning
    st.sidebar.text_input("Your Name", st.session_state.user_name, key="user_name_input")
    st.session_state.user_name = st.session_state.user_name_input
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.sidebar.number_input("Weight (kg)", min_value=30.0, max_value=200.0, value=st.session_state.user_weight, step=0.5, key="user_weight_input")
    with col2:
        st.sidebar.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=st.session_state.user_height, step=1.0, key="user_height_input")
    
    # Update session state values after inputs, required for immediate BMI calc
    st.session_state.user_weight = st.session_state.user_weight_input
    st.session_state.user_height = st.session_state.user_height_input

    bmi, category = calculate_bmi(st.session_state.user_weight, st.session_state.user_height)
    if bmi:
        # ENHANCEMENT: BMI Color-coding
        styled_bmi_category = get_bmi_style(category)
        st.sidebar.info(f"Your BMI: **{bmi}** ({styled_bmi_category})")

    st.sidebar.text_area("Primary Fitness Goals", st.session_state.user_goals, height=100, key="user_goals")

    # Plan Parameters
    st.sidebar.subheader("Plan Parameters")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        st.sidebar.selectbox("Fitness Level", ["Beginner", "Intermediate", "Advanced"], index=["Beginner", "Intermediate", "Advanced"].index(st.session_state.user_level), key="user_level")
    with col4:
        st.sidebar.selectbox("Diet Preference", ["Standard", "Vegetarian", "Vegan", "Keto", "Paleo"], index=["Standard", "Vegetarian", "Vegan", "Keto", "Paleo"].index(st.session_state.user_diet), key="user_diet")
    
    st.sidebar.selectbox("Daily Commitment", ["30 mins", "1 hour", "90 mins+"], index=["30 mins", "1 hour", "90 mins+"].index(st.session_state.user_time), key="user_time")

    # Macro Targets
    st.sidebar.subheader("Daily Macro Targets (Grams)")
    col5, col6, col7 = st.sidebar.columns(3)
    with col5:
        st.sidebar.number_input("Protein", min_value=0, value=st.session_state.macro_protein, step=5, key="macro_protein")
    with col6:
        st.sidebar.number_input("Fat", min_value=0, value=st.session_state.macro_fat, step=5, key="macro_fat")
    with col7:
        st.sidebar.number_input("Carbs", min_value=0, value=st.session_state.macro_carbs, step=5, key="macro_carbs")

    if OFFLINE_MOCK_MODE:
        st.sidebar.warning("⚠️ **OFFLINE MOCK MODE**\n\nAPI keys are missing. Using static mock data.")
    elif not GEMINI_API_KEY:
        st.sidebar.error("❌ **GEMINI API KEY MISSING**\n\nGemini API key is required for generation.")


def render_tab_plan():
    """Renders the plan generation tab."""
    st.header("📝 Generate Personalized Plans")
    
    # FIX: Input validation before plan generation
    weight = st.session_state.user_weight
    height = st.session_state.user_height

    if not (weight > 0 and height > 0 and height >= 100):
        st.warning("Please ensure **Weight (kg)** and **Height (cm)** are valid positive numbers (Height ≥ 100 cm) in the sidebar.")
        return
        
    bmi, _ = calculate_bmi(weight, height)
    
    macro_targets = { 
        "Protein": st.session_state.macro_protein, 
        "Fat": st.session_state.macro_fat, 
        "Carbs": st.session_state.macro_carbs 
    }
    
    # ENHANCEMENT: Macro Targets Validation
    total_macros = macro_targets['Protein'] + macro_targets['Fat'] + macro_targets['Carbs']
    if total_macros < 100:
        st.warning("⚠️ Warning: Your total daily macro target is very low. Adjust values in the sidebar.")
    elif total_macros > 600:
        st.warning("⚠️ Warning: Your total daily macro target is very high. Adjust values in the sidebar.")

    st.divider()

    # --- Workout Plan Generation ---
    st.subheader("🏋️ 7-Day Workout Plan")
    if st.button("Generate Workout Plan", use_container_width=True, type="primary"):
        system_inst = "You are a world-class certified personal trainer. Provide professional, safe, and highly personalized workout advice. Format your output in clean, readable Markdown without any introductory or concluding remarks."
        prompt = f"Generate a detailed 7-day workout plan for {st.session_state.user_name}. Goal: {st.session_state.user_goals}, Level: {st.session_state.user_level}, Time: {st.session_state.user_time}, BMI: {bmi}. Include specific exercises, sets, reps, and a rest day. Start the response with '## Personalized 7-Day Workout Plan'."
        generate_plan(prompt, system_inst, 'workout_plan')

    if st.session_state.workout_plan:
        st.markdown(st.session_state.workout_plan)
        
    st.divider()

    # --- Diet Plan Generation ---
    st.subheader("🥗 7-Day Diet Plan")
    if st.button("Generate Diet Plan", use_container_width=True, type="secondary"):
        system_inst = "You are a world-class certified nutritionist. Provide professional, safe, and highly personalized diet advice. Format your output in clean, readable Markdown without any introductory or concluding remarks."
        prompt = f"Generate a detailed 7-day meal plan suitable for Goal: {st.session_state.user_goals}, BMI: {bmi}, Diet: {st.session_state.user_diet}, Target Macros: {json.dumps(macro_targets)}. Specify meals for Breakfast, Lunch, Dinner, and 2 Snacks. Start the response with '## Personalized 7-Day Meal Plan'."
        generate_plan(prompt, system_inst, 'diet_plan')

    if st.session_state.diet_plan:
        st.markdown(st.session_state.diet_plan)


def render_tab_recipes():
    """Renders the recipe finder tab."""
    st.header("🍽️ Tailored Recipe Finder")
    
    st.info("Recipes are sourced from Spoonacular first, then fall back to structured Gemini generation. **Image display is disabled to reduce token usage and cost.**")

    recipe_query = st.text_input("What kind of recipe are you looking for?", 
                                placeholder="e.g., high-protein chicken dish, keto friendly breakfast", 
                                key="recipe_query_input")

    macro_targets = { 
        "Protein": st.session_state.macro_protein, 
        "Fat": st.session_state.macro_fat, 
        "Carbs": st.session_state.macro_carbs 
    }

    if st.button("Find Recipes", use_container_width=True, type="primary", disabled=not recipe_query):
        find_recipes(recipe_query, macro_targets)

    if st.session_state.recipe_source:
        st.write(f"Source: **{st.session_state.recipe_source}**")
        st.divider()

    recipes = st.session_state.generated_recipes
    if recipes:
        for i, recipe in enumerate(recipes):
            with st.expander(f"**{i+1}. {recipe.get('recipeName')}**", expanded=False):
                
                # --- REMOVED: Image Display (Eliminating high-token usage and use_column_width warning) ---
                
                # --- DESCRIPTION AND SUMMARY (Now displayed sequentially) ---
                st.markdown(f"**Description:** {recipe.get('description', 'N/A')}")
                st.markdown(f"**Summary:** {recipe.get('instructionsSummary', 'N/A')}")

                # --- Macro Pie Chart ---
                macros = recipe.get('macrosGrams', {'protein': 0, 'fat': 0, 'carbs': 0})
                macro_df = pd.DataFrame(macros.items(), columns=['Macro', 'Grams'])
                
                if macro_df['Grams'].sum() > 0:
                    fig = px.pie(macro_df, values='Grams', names='Macro', title='Macronutrient Breakdown (Grams)',
                                 color_discrete_sequence=['#4CAF50', '#FF9800', '#2196F3'])
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    # FIX: All charts use use_container_width=True (no deprecation warning)
                    st.plotly_chart(fig, use_container_width=True) 
                else:
                    st.warning("Macro data unavailable for this recipe.")

                # --- Full Details ---
                st.subheader("Ingredients")
                for ing in recipe.get('ingredients', []):
                    st.markdown(f"- {ing}")

                st.subheader("Full Instructions")
                st.write(recipe.get('fullInstructions', 'N/A'))


def render_tab_grocery():
    """Renders the grocery list tab."""
    st.header("🛒 Generated Grocery List")
    
    recipes = st.session_state.generated_recipes
    if not recipes:
        st.info("Please generate recipes in the 'Recipe Finder' tab first to create a grocery list.")
        return

    # REFACTOR: Use Counter for cleaner aggregation
    all_ingredients = []
    for recipe in recipes:
        for ing in recipe.get('ingredients', []):
            # Basic normalization (split(',')[0] is a simple grouping method)
            clean_ing = ing.split(',')[0].strip().lower() 
            all_ingredients.append(clean_ing)

    ingredients_counter = Counter(all_ingredients)
    
    grocery_list_df = pd.DataFrame({
        'Item': list(ingredients_counter.keys()),
        'Used In (Recipes)': list(ingredients_counter.values())
    }).sort_values(by='Item')

    st.subheader(f"List based on {len(recipes)} recipes")
    st.dataframe(grocery_list_df, use_container_width=True, hide_index=True)

    # Download CSV functionality
    csv = grocery_list_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Grocery List (CSV)",
        data=csv,
        file_name='grocery_list.csv',
        mime='text/csv',
        type="primary"
    )


def render_tab_progress():
    """Renders the progress tracker tab with simulated persistence."""
    st.header("📈 Progress Tracker")
    st.subheader("Log Weight")

    # --- Persistence Note ---
    st.warning("⚠️ **Persistence Note**\n\nData (weight logs) is only saved to the current **session state** and will be lost when you close the tab. For long-term persistence, a database (like Firestore) is required.")
    
    # --- Logging UI ---
    col_date, col_weight, col_btn = st.columns([1, 1, 1])

    with col_date:
        st.session_state.log_date = st.date_input("Date", st.session_state.log_date, key="log_date_input")
    with col_weight:
        st.session_state.log_weight = st.number_input("Weight (kg)", min_value=30.0, max_value=200.0, value=st.session_state.log_weight, step=0.1, key="log_weight_input")
    with col_btn:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True) # Spacer
        if st.button("Log Weight", use_container_width=True, type="primary"):
            log_date_str = st.session_state.log_date.isoformat()
            
            # Check for existing log
            if any(log['date'] == log_date_str for log in st.session_state.weight_logs):
                st.session_state.log_error = True
            else:
                st.session_state.log_error = False
                new_log = {
                    "date": log_date_str,
                    "weight": st.session_state.log_weight,
                    "id": datetime.now().isoformat() 
                }
                st.session_state.weight_logs.append(new_log)
                st.session_state.weight_logs.sort(key=lambda x: x['date'])
                
                # Update main sidebar weight to the latest logged weight
                st.session_state.user_weight_input = st.session_state.log_weight 
                st.success("Weight logged successfully!") 
                # IMPORTANT: No st.experimental_rerun() needed.

    if st.session_state.log_error:
        st.error("A weight log for this date already exists.")

    # --- Display Logs and Deletion ---
    if st.session_state.weight_logs:
        df = pd.DataFrame(st.session_state.weight_logs)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        st.subheader("Weight Trend")
        st.line_chart(df, x='date', y='weight', color='#10B981')

        st.subheader("Log History")
        
        # Display logs in reverse chronological order for history table
        history_df = df.iloc[::-1].copy()
        history_df['Date'] = history_df['date'].dt.strftime('%Y-%m-%d')
        history_df['Weight (kg)'] = history_df['weight']
        
        st.dataframe(history_df[['Date', 'Weight (kg)']], use_container_width=True, hide_index=True)
        
        # Deletion Selectbox
        log_options = [f"{log['date']} ({log['weight']} kg)" for log in st.session_state.weight_logs]
        log_to_delete_str = st.selectbox(
            "Select Log to Delete:", 
            options=["-- Select a log --"] + log_options, 
            index=["-- Select a log --"] + log_options.index(st.session_state.delete_log_select) if st.session_state.delete_log_select in log_options else 0,
            key="delete_log_select_widget"
        )
        # Manually sync the selectbox output to the persistent state variable
        st.session_state.delete_log_select = log_to_delete_str
        
        if st.session_state.delete_log_select != "-- Select a log --":
            
            # Extract date and weight from the selected string
            parts = st.session_state.delete_log_select.split(' ')
            date_str = parts[0]
            weight_val = float(parts[1].strip('()'))

            # Search the original weight_logs array for the index
            try:
                delete_index = next(i for i, log in enumerate(st.session_state.weight_logs) 
                                    if log['date'] == date_str and log['weight'] == weight_val)
                
                if st.button(f"Confirm Delete Log for {date_str}", key="confirm_delete_btn", type="secondary"):
                    # REFACTOR: Deletion handled here. Removing element and setting state causes re-render.
                    st.session_state.weight_logs.pop(delete_index)
                    st.session_state.delete_log_select = "-- Select a log --" # Reset selectbox
                    st.success(f"Log for {date_str} deleted!")
            
            except StopIteration:
                st.error("Could not find selected log for deletion.")

    else:
        st.info("No weight logs recorded yet. Start tracking your progress!")


def render_tab_motivation():
    """Renders the motivation image generation tab."""
    st.header("🌟 Your Daily Motivation")
    
    col_full, col_msg = st.columns([1.5, 1])

    with col_full:
        if st.button("Generate New Motivational Image & Message", use_container_width=True, type="primary", key="generate_both_btn"):
            # 1. Generate Message
            message_system_inst = "You are an encouraging and supportive mental fitness coach. Generate a single, powerful, and inspiring message focused on consistency and overcoming challenges. The message should be appropriate for a banner image."
            generate_plan("Generate a single, powerful, and inspiring message for a gym poster.", message_system_inst, 'motivation_message')
            
            # 2. Generate Image
            if st.session_state.motivation_message:
                generate_image(st.session_state.motivation_message)

    # ENHANCEMENT: Regenerate Message Only Button
    with col_msg:
        if st.button("Regenerate Message Only", use_container_width=True, type="secondary", key="regenerate_msg_btn"):
            message_system_inst = "You are an encouraging and supportive mental fitness coach. Generate a single, powerful, and inspiring message focused on consistency and overcoming challenges. The message should be appropriate for a banner image."
            generate_plan("Generate a single, powerful, and inspiring message for a gym poster.", message_system_inst, 'motivation_message')
            st.success("Message regenerated! Click the primary button to update the image.")


    if st.session_state.motivation_message and st.session_state.motivation_image_url:
        st.subheader("Today's Focus:")
        st.image(st.session_state.motivation_image_url, use_column_width=True)
        st.markdown(f"<p style='text-align: center; font-size: 1.5rem; font-weight: bold; color: #E91E63; margin-top: 10px;'>\"{st.session_state.motivation_message}\"</p>", unsafe_allow_html=True)
    elif st.session_state.motivation_message:
        st.subheader("Message Generated (Image Failed or Mocked):")
        st.markdown(f"<p style='text-align: center; font-size: 1.2rem;'>\"{st.session_state.motivation_message}\"</p>", unsafe_allow_html=True)


# --- 6. MAIN APP LOGIC ---

def main():
    """Main Streamlit application function."""
    st.set_page_config(
        page_title="AI Fitness & Nutrition Planner",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    init_state()
    
    # Render the sidebar inputs
    render_sidebar()

    st.title("AI Fitness & Nutrition Planner")
    st.markdown("---")

    tab_plan, tab_recipe, tab_grocery, tab_progress, tab_motivation = st.tabs([
        "📝 Plan", 
        "🍽️ Recipe", 
        "🛒 Grocery", 
        "📈 Progress", 
        "🌟 Motivation"
    ])

    with tab_plan:
        render_tab_plan()
    
    with tab_recipe:
        render_tab_recipes()

    with tab_grocery:
        render_tab_grocery()

    with tab_progress:
        render_tab_progress()

    with tab_motivation:
        render_tab_motivation()

if __name__ == '__main__':
    main()
