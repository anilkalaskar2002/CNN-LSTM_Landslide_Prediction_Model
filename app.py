from flask import Flask, render_template, jsonify, request
import requests
from datetime import datetime, timedelta
import os
from functools import lru_cache
from werkzeug.exceptions import HTTPException
import logging

app = Flask(__name__)

# API Keys
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY', '51ff32f79dad458681090812252402')
NEWS_API_KEY = '23c1da82cd194f478272b546307c7f1c'

# Weather API configuration
WEATHER_API_BASE_URL = 'https://api.weatherapi.com/v1'
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Cache for weather data
@lru_cache(maxsize=100)
def get_cached_weather(location, timestamp):
    """Cache weather data for each location with a timestamp to ensure freshness"""
    try:
        response = requests.get(
            f'{WEATHER_API_BASE_URL}/forecast.json',
            params={
                'key': WEATHER_API_KEY,
                'q': location,
                'days': 5,  # Increased to 7 days for better forecast
                'aqi': 'yes'  # Include air quality data
            },
            timeout=10  # Add timeout
        )
        response.raise_for_status()  # Raise exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Weather API error: {str(e)}")

# Cache for news data
@lru_cache(maxsize=1)
def get_cached_news(timestamp):
    """Cache news data with a timestamp to ensure freshness"""
    try:
        # First try recent news (last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        response = requests.get(
            'https://newsapi.org/v2/everything',
            params={
                'apiKey': NEWS_API_KEY,
                'q': '(landslide OR landslides) AND (disaster OR warning OR prevention OR monitoring) OR (disaster OR warning OR prevention OR monitoring) OR (rain OR flood OR rain OR flood)',
                'language': 'en',
                'from': week_ago,
                'sortBy': 'publishedAt',
                'pageSize': 6
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # If no recent news, try with a broader date range and more specific search
        if not data.get('articles') or len(data['articles']) < 2:
            three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            
            response = requests.get(
                'https://newsapi.org/v2/everything',
                params={
                    'apiKey': NEWS_API_KEY,
                    'q': ('(landslide OR landslides OR mudslide OR "land slip" OR "ground movement") AND '
                         '(India OR Maharashtra OR Kerala OR Uttarakhand OR Himachal OR Sikkim) AND '
                         '(disaster OR casualties OR damage OR rescue OR warning OR alert)'),
                    'language': 'en',
                    'from': three_months_ago,
                    'sortBy': 'relevancy',  # Change to relevancy for better historical results
                    'pageSize': 6
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # If still no news, try with an even broader search
            if not data.get('articles') or len(data['articles']) < 2:
                response = requests.get(
                    'https://newsapi.org/v2/everything',
                    params={
                        'apiKey': NEWS_API_KEY,
                        'q': ('(landslide OR landslides) AND India AND '
                             '(disaster OR warning OR prevention OR monitoring)'),
                        'language': 'en',
                        'sortBy': 'relevancy',
                        'pageSize': 6
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
        
        # Add source for time context
        if data.get('articles'):
            for article in data['articles']:
                # Add a flag to indicate if this is recent or historical news
                article['is_recent'] = (
                    datetime.strptime(article['publishedAt'], '%Y-%m-%dT%H:%M:%SZ') >
                    datetime.now() - timedelta(days=7)
                )
        
        return data
    except requests.exceptions.RequestException as e:
        raise Exception(f"News API error: {str(e)}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/weather')
def get_weather():
    try:
        location = request.args.get('location', 'Purna,Maharashtra')
        # Create timestamp rounded to CACHE_DURATION
        timestamp = int(datetime.now().timestamp() / CACHE_DURATION) * CACHE_DURATION
        
        # Get weather data from cache or API
        weather_data = get_cached_weather(location, timestamp)
        
        # Add metadata
        weather_data['metadata'] = {
            'cached': True,
            'timestamp': datetime.now().isoformat(),
            'cache_expires_in': CACHE_DURATION - (int(datetime.now().timestamp()) % CACHE_DURATION)
        }
        
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({
            'error': {
                'message': str(e),
                'type': type(e).__name__
            }
        }), 500

@app.route('/api/weather/bulk')
def get_bulk_weather():
    """Endpoint for fetching weather data for multiple locations"""
    try:
        locations = request.args.getlist('locations[]')
        if not locations:
            return jsonify({'error': 'No locations provided'}), 400

        timestamp = int(datetime.now().timestamp() / CACHE_DURATION) * CACHE_DURATION
        results = {}

        for location in locations:
            try:
                results[location] = get_cached_weather(location, timestamp)
            except Exception as e:
                results[location] = {'error': str(e)}

        return jsonify({
            'data': results,
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'locations_processed': len(locations)
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/news')
def get_news():
    try:
        timestamp = int(datetime.now().timestamp() / CACHE_DURATION) * CACHE_DURATION
        news_data = get_cached_news(timestamp)
        
        # Add metadata
        news_data['metadata'] = {
            'cached': True,
            'timestamp': datetime.now().isoformat(),
            'cache_expires_in': CACHE_DURATION - (int(datetime.now().timestamp()) % CACHE_DURATION),
            'has_recent_news': any(article.get('is_recent', False) for article in news_data.get('articles', []))
        }
        
        return jsonify(news_data)
    except Exception as e:
        return jsonify({
            'error': {
                'message': str(e),
                'type': type(e).__name__
            }
        }), 500

@app.route('/weather')
def weather():
    return render_template('weather.html')

@app.route('/predict')
def predict():
    return render_template('predict.html')

@app.route('/map')
def map():
    return render_template('map.html')

@app.route('/more-info')
def more_info():
    return render_template('more_info.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Add a general error handler for other errors
@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return render_template('404.html', 
            error_code=e.code,
            error_name=e.name,
            error_description=e.description
        ), e.code
    
    # Log the error for debugging
    app.logger.error(f'An error occurred: {str(e)}')
    
    return render_template('404.html',
        error_code=500,
        error_name='Internal Server Error',
        error_description='Something went wrong on our end. Please try again later.'
    ), 500

if __name__ == '__main__':
    app.run(debug=True) 