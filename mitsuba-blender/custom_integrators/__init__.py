from .direct import MyDirectIntegrator
from .pssmlt import MyPathIntegrator

def register():
  from mitsuba import register_integrator
  register_integrator("mydirect", lambda props: MyDirectIntegrator(props))
  register_integrator("pssmlt", lambda props: MyPathIntegrator(props))