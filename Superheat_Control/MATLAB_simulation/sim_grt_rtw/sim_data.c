/*
 * sim_data.c
 *
 * Academic License - for use in teaching, academic research, and meeting
 * course requirements at degree granting institutions only.  Not for
 * government, commercial, or other organizational use.
 *
 * Code generation for model "sim".
 *
 * Model version              : 3.0
 * Simulink Coder version : 26.1 (R2026a) 20-Nov-2025
 * C source code generated on : Fri Sep 25 11:31:47 2026
 *
 * Target selection: grt.tlc
 * Note: GRT includes extra infrastructure and instrumentation for prototyping
 * Embedded hardware selection: Intel->x86-64 (Linux 64)
 * Code generation objectives: Unspecified
 * Validation result: Not run
 */

#include "sim.h"

/* Block parameters (default storage) */
P_sim_T sim_P = {
  /* Mask Parameter: DiscreteDerivative_ICPrevScaled
   * Referenced by: '<S3>/UD'
   */
  0.0,

  /* Expression: 1
   * Referenced by: '<S2>/Kp'
   */
  1.0,

  /* Computed Parameter: DiscreteTimeIntegrator_gainval
   * Referenced by: '<S2>/Discrete-Time Integrator'
   */
  0.02,

  /* Expression: 0
   * Referenced by: '<S2>/Discrete-Time Integrator'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<S2>/kd'
   */
  0.0,

  /* Computed Parameter: TSamp_WtEt
   * Referenced by: '<S3>/TSamp'
   */
  50.0,

  /* Expression: 0.5
   * Referenced by: '<S2>/Ki'
   */
  0.5,

  /* Expression: 50
   * Referenced by: '<S1>/Step'
   */
  50.0,

  /* Expression: 8
   * Referenced by: '<S1>/Step'
   */
  8.0,

  /* Expression: 13
   * Referenced by: '<S1>/Step'
   */
  13.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: [0.03572]
   * Referenced by: '<S1>/Discrete Transfer Fcn1'
   */
  0.03572,

  /* Expression: [1  -0.998214]
   * Referenced by: '<S1>/Discrete Transfer Fcn1'
   */
  { 1.0, -0.998214 },

  /* Expression: 0
   * Referenced by: '<S1>/Discrete Transfer Fcn1'
   */
  0.0,

  /* Expression: 0.9
   * Referenced by: '<S1>/Saturation1'
   */
  0.9,

  /* Expression: 0.1
   * Referenced by: '<S1>/Saturation1'
   */
  0.1
};
