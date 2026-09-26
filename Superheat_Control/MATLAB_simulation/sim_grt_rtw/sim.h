/*
 * sim.h
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

#ifndef sim_h_
#define sim_h_
#ifndef sim_COMMON_INCLUDES_
#define sim_COMMON_INCLUDES_
#include "rtwtypes.h"
#include "rtw_continuous.h"
#include "rtw_solver.h"
#include "rt_logging.h"
#include "rt_nonfinite.h"
#include "math.h"
#endif                                 /* sim_COMMON_INCLUDES_ */

#include "sim_types.h"
#include <float.h>
#include <string.h>
#include <stddef.h>

/* Macros for accessing real-time model data structure */
#ifndef rtmGetFinalTime
#define rtmGetFinalTime(rtm)           ((rtm)->Timing.tFinal)
#endif

#ifndef rtmGetRTWLogInfo
#define rtmGetRTWLogInfo(rtm)          ((rtm)->rtwLogInfo)
#endif

#ifndef rtmCounterLimit
#define rtmCounterLimit(rtm, idx)      ((rtm)->Timing.TaskCounters.cLimit[(idx)])
#endif

#ifndef rtmGetErrorStatus
#define rtmGetErrorStatus(rtm)         ((rtm)->errorStatus)
#endif

#ifndef rtmSetErrorStatus
#define rtmSetErrorStatus(rtm, val)    ((rtm)->errorStatus = (val))
#endif

#ifndef rtmStepTask
#define rtmStepTask(rtm, idx)          ((rtm)->Timing.TaskCounters.TID[(idx)] == 0)
#endif

#ifndef rtmGetStopRequested
#define rtmGetStopRequested(rtm)       ((rtm)->Timing.stopRequestedFlag)
#endif

#ifndef rtmSetStopRequested
#define rtmSetStopRequested(rtm, val)  ((rtm)->Timing.stopRequestedFlag = (val))
#endif

#ifndef rtmGetStopRequestedPtr
#define rtmGetStopRequestedPtr(rtm)    (&((rtm)->Timing.stopRequestedFlag))
#endif

#ifndef rtmGetT
#define rtmGetT(rtm)                   (rtmGetTPtr((rtm))[0])
#endif

#ifndef rtmGetTFinal
#define rtmGetTFinal(rtm)              ((rtm)->Timing.tFinal)
#endif

#ifndef rtmGetTPtr
#define rtmGetTPtr(rtm)                ((rtm)->Timing.t)
#endif

#ifndef rtmTaskCounter
#define rtmTaskCounter(rtm, idx)       ((rtm)->Timing.TaskCounters.TID[(idx)])
#endif

/* Block signals (default storage) */
typedef struct {
  real_T Step;                         /* '<S1>/Step' */
  real_T TmpRTBAtPIDInport1;           /* '<S1>/Step' */
  real_T y;                            /* '<S1>/Discrete Transfer Fcn1' */
  real_T ValveOD;                      /* '<S1>/Saturation1' */
  real_T ZeroOrderHold2;               /* '<S2>/Zero-Order Hold2' */
  real_T u;                            /* '<S2>/Zero-Order Hold' */
  real_T e;                            /* '<S2>/Sum' */
  real_T Kp;                           /* '<S2>/Kp' */
  real_T DiscreteTimeIntegrator;       /* '<S2>/Discrete-Time Integrator' */
  real_T kd;                           /* '<S2>/kd' */
  real_T TSamp;                        /* '<S3>/TSamp' */
  real_T Uk1;                          /* '<S3>/UD' */
  real_T Diff;                         /* '<S3>/Diff' */
  real_T Sum1;                         /* '<S2>/Sum1' */
  real_T u_h;                          /* '<S2>/Zero-Order Hold1' */
  real_T Ki;                           /* '<S2>/Ki' */
} B_sim_T;

/* Block states (default storage) for system '<Root>' */
typedef struct {
  real_T DiscreteTransferFcn1_states;  /* '<S1>/Discrete Transfer Fcn1' */
  real_T DiscreteTimeIntegrator_DSTATE;/* '<S2>/Discrete-Time Integrator' */
  real_T UD_DSTATE;                    /* '<S3>/UD' */
  real_T TmpRTBAtPIDInport1_Buf0;      /* synthesized block */
  real_T TmpRTBAtPIDInport1_Buf1;      /* synthesized block */
  real_T TmpRTBAtPIDInport1_Buf2;      /* synthesized block */
  void* TmpRTBAtPIDInport1_d0_SEMAPHORE;/* synthesized block */
  struct {
    void *LoggedData[2];
  } Scope_PWORK;                       /* '<S1>/Scope' */

  struct {
    void *LoggedData[2];
  } Scope_PWORK_e;                     /* '<S2>/Scope' */

  int8_T TmpRTBAtPIDInport1_LstBufWR;  /* synthesized block */
  int8_T TmpRTBAtPIDInport1_RDBuf;     /* synthesized block */
} DW_sim_T;

/* Parameters (default storage) */
struct P_sim_T_ {
  real_T DiscreteDerivative_ICPrevScaled;
                              /* Mask Parameter: DiscreteDerivative_ICPrevScaled
                               * Referenced by: '<S3>/UD'
                               */
  real_T Kp_Gain;                      /* Expression: 1
                                        * Referenced by: '<S2>/Kp'
                                        */
  real_T DiscreteTimeIntegrator_gainval;
                           /* Computed Parameter: DiscreteTimeIntegrator_gainval
                            * Referenced by: '<S2>/Discrete-Time Integrator'
                            */
  real_T DiscreteTimeIntegrator_IC;    /* Expression: 0
                                        * Referenced by: '<S2>/Discrete-Time Integrator'
                                        */
  real_T kd_Gain;                      /* Expression: 0
                                        * Referenced by: '<S2>/kd'
                                        */
  real_T TSamp_WtEt;                   /* Computed Parameter: TSamp_WtEt
                                        * Referenced by: '<S3>/TSamp'
                                        */
  real_T Ki_Gain;                      /* Expression: 0.5
                                        * Referenced by: '<S2>/Ki'
                                        */
  real_T Step_Time;                    /* Expression: 50
                                        * Referenced by: '<S1>/Step'
                                        */
  real_T Step_Y0;                      /* Expression: 8
                                        * Referenced by: '<S1>/Step'
                                        */
  real_T Step_YFinal;                  /* Expression: 13
                                        * Referenced by: '<S1>/Step'
                                        */
  real_T TmpRTBAtPIDInport1_InitialCondi;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T DiscreteTransferFcn1_NumCoef; /* Expression: [0.03572]
                                        * Referenced by: '<S1>/Discrete Transfer Fcn1'
                                        */
  real_T DiscreteTransferFcn1_DenCoef[2];/* Expression: [1  -0.998214]
                                          * Referenced by: '<S1>/Discrete Transfer Fcn1'
                                          */
  real_T DiscreteTransferFcn1_InitialSta;/* Expression: 0
                                          * Referenced by: '<S1>/Discrete Transfer Fcn1'
                                          */
  real_T Saturation1_UpperSat;         /* Expression: 0.9
                                        * Referenced by: '<S1>/Saturation1'
                                        */
  real_T Saturation1_LowerSat;         /* Expression: 0.1
                                        * Referenced by: '<S1>/Saturation1'
                                        */
};

/* Real-time Model Data Structure */
struct tag_RTM_sim_T {
  const char_T *errorStatus;
  RTWLogInfo *rtwLogInfo;
  RTWSolverInfo solverInfo;

  /*
   * Timing:
   * The following substructure contains information regarding
   * the timing information for the model.
   */
  struct {
    uint32_T clockTick0;
    uint32_T clockTickH0;
    time_T stepSize0;
    uint32_T clockTick1;
    uint32_T clockTickH1;
    struct {
      uint8_T TID[3];
      uint8_T cLimit[3];
    } TaskCounters;

    time_T tFinal;
    SimTimeStep simTimeStep;
    boolean_T stopRequestedFlag;
    time_T *t;
    time_T tArray[3];
  } Timing;
};

/* Block parameters (default storage) */
extern P_sim_T sim_P;

/* Block signals (default storage) */
extern B_sim_T sim_B;

/* Block states (default storage) */
extern DW_sim_T sim_DW;

/* Model entry point functions */
extern void sim_initialize(void);
extern void sim_step0(void);           /* Sample time: [0.0s, 0.0s] */
extern void sim_step2(void);           /* Sample time: [0.02s, 0.0s] */
extern void sim_terminate(void);

/* Real-time Model object */
extern RT_MODEL_sim_T *const sim_M;

/*-
 * The generated code includes comments that allow you to trace directly
 * back to the appropriate location in the model.  The basic format
 * is <system>/block_name, where system is the system number (uniquely
 * assigned by Simulink) and block_name is the name of the block.
 *
 * Use the MATLAB hilite_system command to trace the generated code back
 * to the model.  For example,
 *
 * hilite_system('<S3>')    - opens system 3
 * hilite_system('<S3>/Kp') - opens and selects block Kp which resides in S3
 *
 * Here is the system hierarchy for this model
 *
 * '<Root>' : 'sim'
 * '<S1>'   : 'sim/Model'
 * '<S2>'   : 'sim/Model/PID'
 * '<S3>'   : 'sim/Model/PID/Discrete Derivative'
 */
#endif                                 /* sim_h_ */
