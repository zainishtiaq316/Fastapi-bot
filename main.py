"""
E-commerce Order Assistant Bot with FastAPI and Gemini AI
Auto-loads data from database and responds using cached data
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pyodbc
import json
import os
from datetime import datetime
import schedule
import time
from threading import Thread
import google.generativeai as genai
from typing import Optional

# ============== Configuration ==============
DB_CONFIG = {
    'server': '192.168.0.1',
    'user': 'sa',
    'password': 'Core100',
    'database': 'ecommerce'
}

GEMINI_API_KEY = "AIzaSyB5pe-tfnuqKegkwlDmKYgayhd_njfh_rM"
DATA_FILE = "hp_order_data.json"
REFRESH_INTERVAL_MINUTES = 5  # Har 5 minute mein data refresh hoga

# ============== FastAPI App ==============
app = FastAPI(title="E-commerce Order Bot", version="1.0")

# ============== Gemini AI Setup ==============
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# ============== Database Functions ==============
def get_db_connection():
    """Database connection banata hai"""
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"UID={DB_CONFIG['user']};"
            f"PWD={DB_CONFIG['password']}"
        )
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def load_orders_from_db():
    """Database se orders load karta hai aur file mein save karta hai"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hp_order")
        
        # Column names get karo
        columns = [column[0] for column in cursor.description]
        
        # Data fetch karo
        orders = []
        for row in cursor.fetchall():
            order_dict = dict(zip(columns, row))
            # DateTime objects ko string mein convert karo
            for key, value in order_dict.items():
                if isinstance(value, datetime):
                    order_dict[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            orders.append(order_dict)
        
        # File mein save karo
        data_to_save = {
            'orders': orders,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_orders': len(orders)
        }
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        
        conn.close()
        print(f"✅ Data loaded successfully! Total orders: {len(orders)}")
        return True
        
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return False

def load_orders_from_file():
    """File se orders load karta hai"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None

# ============== Background Data Refresh ==============
def refresh_data_job():
    """Background mein data refresh karta hai"""
    while True:
        print(f"🔄 Refreshing data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        load_orders_from_db()
        time.sleep(REFRESH_INTERVAL_MINUTES * 60)

def start_background_refresh():
    """Background thread start karta hai"""
    thread = Thread(target=refresh_data_job, daemon=True)
    thread.start()

# ============== AI Query Handler ==============
def query_with_gemini(user_query: str, orders_data: dict):
    """Gemini AI se query ka answer leta hai"""
    try:
        # Context prepare karo
        context = f"""
Tum ek helpful e-commerce order assistant ho. Tumhare paas ye orders ka data hai:

Total Orders: {orders_data['total_orders']}
Last Updated: {orders_data['last_updated']}

Orders Data:
{json.dumps(orders_data['orders'][:50], indent=2, ensure_ascii=False)}

Note: Agar 50 se zyada orders hain to sirf pehle 50 dikhaaye gaye hain analysis ke liye.

User ka sawal: {user_query}

Instructions:
- Urdu aur English mix mein jawab do (user friendly)
- Data ke base pe accurate answer do
- Agar specific order ki details chahiye to order ID ya customer name use karo
- Summary ya statistics chahiye to clear format mein do
- Agar data mein nahi hai to honestly bata do
"""
        
        response = model.generate_content(context)
        return response.text
        
    except Exception as e:
        return f"AI response error: {str(e)}"

# ============== API Models ==============
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    data_info: dict
    timestamp: str

# ============== API Endpoints ==============
@app.on_event("startup")
async def startup_event():
    """App start hone pe pehli baar data load karo"""
    print("🚀 Starting E-commerce Order Bot...")
    print("📊 Loading initial data from database...")
    load_orders_from_db()
    print("🔄 Starting background data refresh...")
    start_background_refresh()
    print("✅ Bot is ready!")

@app.get("/")
async def root():
    """Health check endpoint"""
    data = load_orders_from_file()
    if data:
        return {
            "status": "running",
            "message": "E-commerce Order Bot is active!",
            "data_info": {
                "total_orders": data['total_orders'],
                "last_updated": data['last_updated']
            }
        }
    return {"status": "running", "message": "Waiting for data to load..."}

@app.post("/query", response_model=QueryResponse)
async def query_orders(request: QueryRequest):
    """User query ka jawab deta hai (file se data use karke)"""
    try:
        # File se data load karo
        data = load_orders_from_file()
        
        if not data:
            raise HTTPException(status_code=503, detail="Data not loaded yet. Please try again.")
        
        # Gemini AI se query process karo
        answer = query_with_gemini(request.query, data)
        
        return QueryResponse(
            answer=answer,
            data_info={
                "total_orders": data['total_orders'],
                "last_updated": data['last_updated']
            },
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refresh-data")
async def manual_refresh(background_tasks: BackgroundTasks):
    """Manually data refresh karo"""
    background_tasks.add_task(load_orders_from_db)
    return {"message": "Data refresh started in background"}

@app.get("/data-stats")
async def get_data_stats():
    """Current data ki statistics"""
    data = load_orders_from_file()
    if not data:
        return {"message": "No data available"}
    
    return {
        "total_orders": data['total_orders'],
        "last_updated": data['last_updated'],
        "sample_order": data['orders'][0] if data['orders'] else None
    }

# ============== Run karne ka tareeqa ==============
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)