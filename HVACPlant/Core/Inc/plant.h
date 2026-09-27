#ifndef PLANT_H
#define PLANT_H

typedef struct
{
  double num;    /* numerator coefficient b0 */
  double den;    /* denominator coefficient a1 (pole), transfer function num / (z - den) */
  double num_d;  /* disturbance numerator coefficient, same pole as the valve path */
  double y_prev; /* y[n-1] */
  double u_prev; /* u[n-1] */
  double d_prev; /* d[n-1] */
} Plant_t;

/* Discrete coefficients for num/(z-den) at Ts = 1.0s
 * Continuous-time first-order plant
 * G(s) = K/(tau*s + 1) via den = exp(-Ts/tau), num = K*(1-den):
 *   tau ~= 5.594 s, K = 20.0 (DC gain)*/
#define PLANT_TS       1.0
#define PLANT_NUM      3.273862869
#define PLANT_DEN      0.836306857

/* Ambient temperature load disturbance, measured by Board 1's BME280.
 * A warmer room raises the evaporator's heat load, which pushes superheat up.
 * Modelled as a second input through the same first-order lag as the valve,
 * Gd(s) = Kd/(tau*s + 1), so num_d = Kd*(1-den) shares the plant's pole.
 * The disturbance is the deviation from PLANT_AMBIENT_REF_DEGC, so a room at
 * the reference temperature leaves the original plant unchanged. */
#define PLANT_AMBIENT_REF_DEGC  22.0
#define PLANT_AMBIENT_GAIN      0.5 /* Kd: degC superheat per degC ambient deviation */
#define PLANT_NUM_AMBIENT       (PLANT_AMBIENT_GAIN * (1.0 - PLANT_DEN))

void Plant_Init(Plant_t *plant, double num, double den, double num_d, double y0);
double Plant_Update(Plant_t *plant, double u, double d);

#endif /* PLANT_H */
