#include "pid.h"

void PID_Init(PID_t *pid, double kp, double ki, double ts, double out_min, double out_max)
{
  pid->kp = kp;
  pid->ki = ki;
  pid->ts = ts;
  pid->out_min = out_min;
  pid->out_max = out_max;
  pid->integrator = 0.0;
}

/* Discrete PI controller, ported from the Simulink PID subsystem (Kp=1, Ki=0.5,
 * Kd=0 currently unused). Output is saturated to [out_min, out_max] with
 * clamping anti-windup so the integrator doesn't keep growing while saturated.
 * ts must equal the real time between calls. */
double PID_Update(PID_t *pid, double setpoint, double measurement)
{
  double error = setpoint - measurement;

  pid->integrator += pid->ki * error * pid->ts;

  double u = pid->kp * error + pid->integrator;

  if (u > pid->out_max)
  {
    pid->integrator -= (u - pid->out_max);
    u = pid->out_max;
  }
  else if (u < pid->out_min)
  {
    pid->integrator += (pid->out_min - u);
    u = pid->out_min;
  }

  return u;
}
