const WEATHER_ENDPOINT = 'https://api.open-meteo.com/v1/forecast?latitude=51.9244&longitude=4.4777&current=temperature_2m,weather_code,cloud_cover,rain,showers,snowfall,wind_speed_10m&hourly=visibility&forecast_hours=2&past_hours=1&timezone=Europe%2FAmsterdam&timeformat=unixtime';

export const rotterdamTime = date => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Amsterdam', hour: '2-digit', minute: '2-digit' }).format(date);

export function weatherDescription(code) {
  if (code === 0) return 'Clear sky';
  if (code === 1) return 'Mostly clear';
  if (code === 2) return 'Partly cloudy';
  if (code === 3) return 'Overcast';
  if ([45, 48].includes(code)) return 'Fog';
  if ([51, 53, 55, 56, 57].includes(code)) return 'Drizzle';
  if ([61, 63, 65, 66, 67].includes(code)) return 'Rain';
  if ([71, 73, 75, 77].includes(code)) return 'Snow';
  if ([80, 81, 82].includes(code)) return 'Rain showers';
  if ([85, 86].includes(code)) return 'Snow showers';
  if ([95, 96, 99].includes(code)) return 'Thunderstorms';
  return 'Weather unavailable';
}

export function weatherStateFromForecast({current,hourly}) {
  if(!Number.isFinite(current?.temperature_2m)||!Number.isFinite(current?.time))throw new Error('Weather response is incomplete');
  const visibilityIndex=hourly?.time?.findLastIndex(time=>time<=current.time&&current.time-time<=3600)??-1;
  const visibility=visibilityIndex>=0?hourly.visibility?.[visibilityIndex]:null;
  return {available:true,temperature:current.temperature_2m,code:current.weather_code,description:weatherDescription(current.weather_code),cloudCover:current.cloud_cover,
    rain:Math.max(0,Number(current.rain)||0)+Math.max(0,Number(current.showers)||0),snow:Math.max(0,Number(current.snowfall)||0),
    visibility:Number.isFinite(visibility)&&visibility>0?visibility:null,wind:current.wind_speed_10m,date:new Date(current.time*1000)};
}

export function watchWeather(onUpdate) {
  let disposed = false;
  let request;
  async function refresh() {
    request?.abort();
    request = new AbortController();
    const timeout = setTimeout(() => request.abort(), 15000);
    try {
      const response = await fetch(WEATHER_ENDPOINT, { signal: request.signal });
      if (!response.ok) throw new Error(`Weather request returned ${response.status}`);
      const forecast=await response.json();
      if (!disposed) onUpdate(weatherStateFromForecast(forecast));
    } catch (error) {
      if (!disposed) onUpdate({ available: false, error: error.message });
    } finally { clearTimeout(timeout); }
  }
  refresh();
  const timer = setInterval(refresh, 15 * 60 * 1000);
  return () => { disposed = true; clearInterval(timer); request?.abort(); };
}
