#ifndef PID_H
#define PID_H

typedef struct
{
  double kp;
  double ki;
  double ts;
  double out_min;
  double out_max;
  double integrator;
} PID_t;

void PID_Init(PID_t *pid, double kp, double ki, double ts, double out_min, double out_max);
double PID_Update(PID_t *pid, double setpoint, double measurement);

#endif /* PID_H */
