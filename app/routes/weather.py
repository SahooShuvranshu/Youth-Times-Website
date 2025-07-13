from flask import Blueprint, jsonify, request, current_app
from ..weather import WeatherService
import logging

logger = logging.getLogger(__name__)

weather_bp = Blueprint('weather', __name__)

@weather_bp.route('/api/weather')
def get_weather():
    """
    API endpoint to get current weather data
    Query parameter: city (optional, defaults to Bhubaneswar)
    """
    try:
        city = request.args.get('city', 'Bhubaneswar')
        weather_data = WeatherService.get_weather_by_city(city)
        
        if weather_data:
            return jsonify({
                'success': True,
                'data': weather_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Unable to fetch weather data'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in weather API: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@weather_bp.route('/api/weather/forecast')
def get_forecast():
    """
    API endpoint to get weather forecast
    Query parameters: city (optional), days (optional, defaults to 5)
    """
    try:
        city = request.args.get('city', 'Bhubaneswar')
        days = int(request.args.get('days', 5))
        
        # Limit days to reasonable range
        days = max(1, min(days, 7))
        
        forecast_data = WeatherService.get_forecast(city, days)
        
        if forecast_data:
            return jsonify({
                'success': True,
                'data': forecast_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Unable to fetch forecast data'
            }), 500
            
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'Invalid days parameter'
        }), 400
    except Exception as e:
        logger.error(f"Error in forecast API: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@weather_bp.route('/api/weather/widget')
def get_weather_widget():
    """
    API endpoint for simplified weather widget data
    """
    try:
        city = request.args.get('city', 'Bhubaneswar')
        weather_data = WeatherService.get_weather_widget_data(city)
        
        if weather_data:
            return jsonify({
                'success': True,
                'data': weather_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Unable to fetch weather data'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in weather widget API: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

# Export blueprint for import in __init__.py
bp = weather_bp
