// Written by AI, GPT-6, 2026-10-24.
// Viewing illumination, not a measurement of Rotterdam's sky or luminaires.
// Local surface light continues to come from retained municipal fixture heads.
export function miniatureLighting({night=0,golden=false,cloud=0}={}) {
  const t=Math.max(0,Math.min(1,night));
  const day={sun:golden?'#ffc077':'#fff4e4',sky:golden?'#e2dcc9':'#d9e0e5',ground:'#a09885',background:golden?'#cfc5ab':'#adc8c7',sunIntensity:(golden?2.8:2.6)*(1-cloud*.68),skyIntensity:1.45+cloud*.35};
  // Neutral dim skylight retains source paint colours. The previous saturated
  // blue key and equally strong blue hemisphere made all surfaces look alike.
  const dark={sun:'#c1c7ce',sky:'#a4afb9',ground:'#55504a',background:'#18232b',sunIntensity:.27,skyIntensity:.46};
  return {day,dark,night:t};
}

export function applyMiniatureLighting({sun,sky,background},state) {
  const {day,dark,night}=miniatureLighting(state);
  sun.color.set(day.sun).lerp(sun.color.clone().set(dark.sun),night);
  sky.color.set(day.sky).lerp(sky.color.clone().set(dark.sky),night);
  sky.groundColor.set(day.ground).lerp(sky.groundColor.clone().set(dark.ground),night);
  background.set(day.background).lerp(background.clone().set(dark.background),night);
  sun.intensity=day.sunIntensity+(dark.sunIntensity-day.sunIntensity)*night;
  sky.intensity=day.skyIntensity+(dark.skyIntensity-day.skyIntensity)*night;
}
