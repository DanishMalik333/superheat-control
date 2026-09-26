#ifndef PLANT_H
#define PLANT_H

typedef struct
{
  double num;    /* numerator coefficient b0 */
  double den;    /* denominator coefficient a1 (pole), transfer function num / (z - den) */
  double y_prev; /* y[n-1] */
  double u_prev; /* u[n-1] */
} Plant_t;

/* Discrete coefficients for num/(z-den) at Ts = 1.0s, re-derived from the
 * Simulink model's original Ts = 0.01s discretization (num=0.03572,
 * den=0.998214). Recovering the underlying continuous-time first-order plant
 * G(s) = K/(tau*s + 1) via den = exp(-Ts/tau), num = K*(1-den):
 *   tau ~= 5.594 s, K = 20.0 (DC gain)
 * then re-discretizing (ZOH) at Ts = 1.0s gives the values below. Ki/Kp in
 * pid.h do NOT need rescaling for the new Ts -- PID_Update's integrator term
 * (Ki * error * ts) already accounts for Ts as a rate, so Ki stays a valid
 * per-second gain regardless of sample period. If the Simulink model's plant
 * or PID blocks are ever changed, recompute both these coefficients and Ki
 * together and update this comment. */
#define PLANT_TS       1.0
#define PLANT_NUM      3.273862869
#define PLANT_DEN      0.836306857

void Plant_Init(Plant_t *plant, double num, double den, double y0);
double Plant_Update(Plant_t *plant, double u);

#endif /* PLANT_H */
