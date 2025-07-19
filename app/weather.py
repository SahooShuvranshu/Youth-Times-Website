import requests
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class WeatherService:
    """Service for fetching weather data from OpenWeather API"""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    @staticmethod
    def get_weather_by_city(city_name="Bhubaneswar"):
        """
        Get current weather for a city
        Default to Bhubaneswar (capital of Odisha) for Youth Times
        """
        try:
            api_key = current_app.config.get('OPENWEATHER_API_KEY')
            if not api_key:
                logger.error("OpenWeather API key not configured")
                return None
                
            url = f"{WeatherService.BASE_URL}/weather"
            params = {
                'q': city_name,
                'appid': api_key,
                'units': 'metric'  # Use Celsius
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract and format the weather data
            weather_data = {
                'city': data['name'],
                'country': data['sys']['country'],
                'temperature': round(data['main']['temp']),
                'feels_like': round(data['main']['feels_like']),
                'humidity': data['main']['humidity'],
                'description': data['weather'][0]['description'].title(),
                'icon': data['weather'][0]['icon'],
                'wind_speed': data['wind']['speed'],
                'pressure': data['main']['pressure'],
                'visibility': data.get('visibility', 0) // 1000,  # Convert to km
                'icon_url': f"https://openweathermap.org/img/wn/{data['weather'][0]['icon']}@2x.png"
            }
            
            return weather_data
            
        except requests.exceptions.Timeout:
            logger.error("Weather API request timed out")
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
        Get weather forecast for a city
        Returns forecast for the next 5 days
        """
        try:
            api_key = current_app.config.get('OPENWEATHER_API_KEY')
            if not api_key:
                logger.error("OpenWeather API key not configured")
                return None
                
            url = f"{WeatherService.BASE_URL}/forecast"
            params = {
                'q': city_name,
                'appid': api_key,
                'units': 'metric',
                'cnt': days * 8  # 8 forecasts per day (every 3 hours)
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Group forecasts by day
            daily_forecasts = []
            current_date = None
            daily_data = None
            
            for forecast in data['list']:
                date = forecast['dt_txt'].split(' ')[0]
                
                if date != current_date:
                    if daily_data:
                        daily_forecasts.append(daily_data)
                    
                    current_date = date
                    daily_data = {
                        'date': date,
                        'temp_min': forecast['main']['temp_min'],
                        'temp_max': forecast['main']['temp_max'],
                        'description': forecast['weather'][0]['description'].title(),
                        'icon': forecast['weather'][0]['icon'],
                        'icon_url': f"https://openweathermap.org/img/wn/{forecast['weather'][0]['icon']}@2x.png"
                    }
                else:
                    # Update min/max temps for the day
                    daily_data['temp_min'] = min(daily_data['temp_min'], forecast['main']['temp_min'])
                    daily_data['temp_max'] = max(daily_data['temp_max'], forecast['main']['temp_max'])
            
            # Add the last day
            if daily_data:
                daily_forecasts.append(daily_data)
            
            # Round temperatures
            for day in daily_forecasts:
                day['temp_min'] = round(day['temp_min'])
                day['temp_max'] = round(day['temp_max'])
            
            return daily_forecasts[:days]  # Return only requested number of days
            
        except requests.exceptions.Timeout:
            logger.error("Weather forecast API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather forecast: {e}")
            return None
        except KeyError as e:
            logger.error(f"Error parsing weather forecast data: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in weather forecast: {e}")
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
