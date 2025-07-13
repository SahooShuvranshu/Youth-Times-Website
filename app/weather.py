import requests
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class WeatherService:
    """Service for fetching weather data from WeatherAPI.com"""
    BASE_URL = "http://api.weatherapi.com/v1"

    @staticmethod
    def get_weather_by_city(city_name="Bhubaneswar"):
        """
        Get current weather for a city using WeatherAPI.com
        """
        try:
            api_key = current_app.config.get('WEATHER_API_KEY')
            if not api_key:
                logger.error("WeatherAPI key not configured")
                return None

            url = f"{WeatherService.BASE_URL}/current.json"
            params = {
                'key': api_key,
                'q': city_name,
                'aqi': 'no'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            current = data['current']
            location = data['location']
            weather_data = {
                'city': location['name'],
                'country': location['country'],
                'temperature': round(current['temp_c']),
                'feels_like': round(current['feelslike_c']),
                'humidity': current['humidity'],
                'description': current['condition']['text'],
                'icon': current['condition']['icon'],
                'wind_speed': current['wind_kph'],
                'pressure': current['pressure_mb'],
                'visibility': current['vis_km'],
                'icon_url': f"https:{current['condition']['icon']}"
            }
            return weather_data
        except requests.exceptions.Timeout:
            logger.error("WeatherAPI request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather data: {e}")
            return None
        except KeyError as e:
            logger.error(f"Error parsing weather data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in weather service: {e}")
            return None

    @staticmethod
    def get_forecast(city_name="Bhubaneswar", days=5):
        """
        Get weather forecast for a city using WeatherAPI.com
        Returns forecast for the next 'days' days
        """
        try:
            api_key = current_app.config.get('WEATHER_API_KEY')
            if not api_key:
                logger.error("WeatherAPI key not configured")
                return None

            url = f"{WeatherService.BASE_URL}/forecast.json"
            params = {
                'key': api_key,
                'q': city_name,
                'days': days,
                'aqi': 'no',
                'alerts': 'no'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            daily_forecasts = []
            for day in data['forecast']['forecastday']:
                daily_data = {
                    'date': day['date'],
                    'temp_min': day['day']['mintemp_c'],
                    'temp_max': day['day']['maxtemp_c'],
                    'description': day['day']['condition']['text'],
                    'icon': day['day']['condition']['icon'],
                    'icon_url': f"https:{day['day']['condition']['icon']}"
                }
                daily_forecasts.append(daily_data)
            return daily_forecasts
        except requests.exceptions.Timeout:
            logger.error("WeatherAPI request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather forecast: {e}")
            return None
        except KeyError as e:
            logger.error(f"Error parsing weather forecast: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in weather forecast service: {e}")
            return None

    @staticmethod
    def get_weather_widget_data(city_name="Bhubaneswar"):
        """
        Get simplified weather data for the main widget
        """
        weather_data = WeatherService.get_weather_by_city(city_name)
        if not weather_data:
            return None
        return {
            'city': weather_data['city'],
            'temperature': weather_data['temperature'],
            'description': weather_data['description'],
            'icon_url': weather_data['icon_url'],
            'humidity': weather_data['humidity'],
            'wind_speed': weather_data['wind_speed']
        }
