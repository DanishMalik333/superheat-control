#ifndef PLANT_H
#define PLANT_H

typedef struct
{
  double num;    /* numerator coefficient b0 */
  double den;    /* denominator coefficient a1 (pole), transfer function num / (z - den) */
  double y_prev; /* y[n-1] */
  double u_prev; /* u[n-1] */
} Plant_t;

/* num/(z-den) at Ts=1.0s. Re-discretized (ZOH) from tau~=5.594s, K=20.0. */
#define PLANT_TS       1.0
#define PLANT_NUM      3.273862869
#define PLANT_DEN      0.836306857

void Plant_Init(Plant_t *plant, double num, double den, double y0);
double Plant_Update(Plant_t *plant, double u);

#endif /* PLANT_H */
