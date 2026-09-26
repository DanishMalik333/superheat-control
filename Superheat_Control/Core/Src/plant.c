#include "plant.h"

void Plant_Init(Plant_t *plant, double num, double den, double y0)
{
  plant->num = num;
  plant->den = den;
  plant->y_prev = y0;
  plant->u_prev = 0.0;
}

/* y[n] = den*y[n-1] + num*u[n-1]. Call once per control cycle at Ts. */
double Plant_Update(Plant_t *plant, double u)
{
  double y = plant->den * plant->y_prev + plant->num * plant->u_prev;

  plant->y_prev = y;
  plant->u_prev = u;

  return y;
}
