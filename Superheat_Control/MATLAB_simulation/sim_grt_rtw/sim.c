/*
 * sim.c
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
#include "rtw_windows.h"
#include "rtwtypes.h"
#include "sim_private.h"
#include <string.h>

/* Block signals (default storage) */
B_sim_T sim_B;

/* Block states (default storage) */
DW_sim_T sim_DW;

/* Real-time model */
static RT_MODEL_sim_T sim_M_;
RT_MODEL_sim_T *const sim_M = &sim_M_;

/* Model step function for TID0 */
void sim_step0(void)                   /* Sample time: [0.0s, 0.0s] */
{
  real_T currentTime;
  int8_T wrBufIdx;

  /* Step: '<S1>/Step' */
  currentTime = sim_M->Timing.t[0];
  if (currentTime < sim_P.Step_Time) {
    /* Step: '<S1>/Step' */
    sim_B.Step = sim_P.Step_Y0;
  } else {
    /* Step: '<S1>/Step' */
    sim_B.Step = sim_P.Step_YFinal;
  }

  /* End of Step: '<S1>/Step' */

  /* RateTransition generated from: '<S1>/PID' */
  rtw_win_mutex_wait(sim_DW.TmpRTBAtPIDInport1_d0_SEMAPHORE);
  wrBufIdx = (int8_T)(sim_DW.TmpRTBAtPIDInport1_LstBufWR + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx == sim_DW.TmpRTBAtPIDInport1_RDBuf) {
    wrBufIdx++;
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_win_mutex_release(sim_DW.TmpRTBAtPIDInport1_d0_SEMAPHORE);
  switch (wrBufIdx) {
   case 0:
    sim_DW.TmpRTBAtPIDInport1_Buf0 = sim_B.Step;
    break;

   case 1:
    sim_DW.TmpRTBAtPIDInport1_Buf1 = sim_B.Step;
    break;

   case 2:
    sim_DW.TmpRTBAtPIDInport1_Buf2 = sim_B.Step;
    break;
  }

  sim_DW.TmpRTBAtPIDInport1_LstBufWR = wrBufIdx;

  /* End of RateTransition generated from: '<S1>/PID' */

  /* Matfile logging */
  rt_UpdateTXYLogVars(sim_M->rtwLogInfo, (sim_M->Timing.t));

  /* signal main to stop simulation */
  {                                    /* Sample time: [0.0s, 0.0s] */
    if ((rtmGetTFinal(sim_M)!=-1) &&
        !((rtmGetTFinal(sim_M)-sim_M->Timing.t[0]) > sim_M->Timing.t[0] *
          (DBL_EPSILON))) {
      rtmSetErrorStatus(sim_M, "Simulation finished");
    }
  }

  /* Update absolute time */
  /* The "clockTick0" counts the number of times the code of this task has
   * been executed. The absolute time is the multiplication of "clockTick0"
   * and "Timing.stepSize0". Size of "clockTick0" ensures timer will not
   * overflow during the application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick0 and the high bits
   * Timing.clockTickH0. When the low bit overflows to 0, the high bits increment.
   */
  if (!(++sim_M->Timing.clockTick0)) {
    ++sim_M->Timing.clockTickH0;
  }

  sim_M->Timing.t[0] = sim_M->Timing.clockTick0 * sim_M->Timing.stepSize0 +
    sim_M->Timing.clockTickH0 * sim_M->Timing.stepSize0 * 4294967296.0;

  /* Update absolute time */
  /* The "clockTick1" counts the number of times the code of this task has
   * been executed. The resolution of this integer timer is 0.01, which is the step size
   * of the task. Size of "clockTick1" ensures timer will not overflow during the
   * application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick1 and the high bits
   * Timing.clockTickH1. When the low bit overflows to 0, the high bits increment.
   */
  sim_M->Timing.clockTick1++;
  if (!sim_M->Timing.clockTick1) {
    sim_M->Timing.clockTickH1++;
  }
}

/* Model step function for TID2 */
void sim_step2(void)                   /* Sample time: [0.02s, 0.0s] */
{
  {
    real_T numAccum;
    real_T u1;
    real_T u2;

    /* RateTransition generated from: '<S1>/PID' */
    rtw_win_mutex_wait(sim_DW.TmpRTBAtPIDInport1_d0_SEMAPHORE);
    sim_DW.TmpRTBAtPIDInport1_RDBuf = sim_DW.TmpRTBAtPIDInport1_LstBufWR;
    rtw_win_mutex_release(sim_DW.TmpRTBAtPIDInport1_d0_SEMAPHORE);
    switch (sim_DW.TmpRTBAtPIDInport1_RDBuf) {
     case 0:
      /* RateTransition generated from: '<S1>/PID' */
      sim_B.TmpRTBAtPIDInport1 = sim_DW.TmpRTBAtPIDInport1_Buf0;
      break;

     case 1:
      /* RateTransition generated from: '<S1>/PID' */
      sim_B.TmpRTBAtPIDInport1 = sim_DW.TmpRTBAtPIDInport1_Buf1;
      break;

     case 2:
      /* RateTransition generated from: '<S1>/PID' */
      sim_B.TmpRTBAtPIDInport1 = sim_DW.TmpRTBAtPIDInport1_Buf2;
      break;
    }

    /* End of RateTransition generated from: '<S1>/PID' */

    /* DiscreteTransferFcn: '<S1>/Discrete Transfer Fcn1' */
    numAccum = sim_P.DiscreteTransferFcn1_NumCoef *
      sim_DW.DiscreteTransferFcn1_states;

    /* DiscreteTransferFcn: '<S1>/Discrete Transfer Fcn1' */
    sim_B.y = numAccum;

    /* Outputs for Atomic SubSystem: '<S1>/PID' */
    /* ZeroOrderHold: '<S2>/Zero-Order Hold2' */
    sim_B.ZeroOrderHold2 = sim_B.TmpRTBAtPIDInport1;

    /* ZeroOrderHold: '<S2>/Zero-Order Hold' */
    sim_B.u = sim_B.y;

    /* Sum: '<S2>/Sum' */
    sim_B.e = sim_B.ZeroOrderHold2 - sim_B.u;

    /* Gain: '<S2>/Kp' */
    sim_B.Kp = sim_P.Kp_Gain * sim_B.e;

    /* DiscreteIntegrator: '<S2>/Discrete-Time Integrator' */
    sim_B.DiscreteTimeIntegrator = sim_DW.DiscreteTimeIntegrator_DSTATE;

    /* Gain: '<S2>/kd' */
    sim_B.kd = sim_P.kd_Gain * sim_B.e;

    /* SampleTimeMath: '<S3>/TSamp'
     *
     * About '<S3>/TSamp':
     *  y = u * K where K = 1 / ( w * Ts )
     *   */
    sim_B.TSamp = sim_B.kd * sim_P.TSamp_WtEt;

    /* UnitDelay: '<S3>/UD' */
    sim_B.Uk1 = sim_DW.UD_DSTATE;

    /* Sum: '<S3>/Diff' */
    sim_B.Diff = sim_B.TSamp - sim_B.Uk1;

    /* Sum: '<S2>/Sum1' */
    sim_B.Sum1 = (sim_B.Kp + sim_B.DiscreteTimeIntegrator) + sim_B.Diff;

    /* ZeroOrderHold: '<S2>/Zero-Order Hold1' */
    sim_B.u_h = sim_B.Sum1;

    /* Gain: '<S2>/Ki' */
    sim_B.Ki = sim_P.Ki_Gain * sim_B.e;

    /* End of Outputs for SubSystem: '<S1>/PID' */

    /* Saturate: '<S1>/Saturation1' */
    numAccum = sim_B.u_h;
    u1 = sim_P.Saturation1_LowerSat;
    u2 = sim_P.Saturation1_UpperSat;
    if (numAccum > u2) {
      /* Saturate: '<S1>/Saturation1' */
      sim_B.ValveOD = u2;
    } else if (numAccum < u1) {
      /* Saturate: '<S1>/Saturation1' */
      sim_B.ValveOD = u1;
    } else {
      /* Saturate: '<S1>/Saturation1' */
      sim_B.ValveOD = numAccum;
    }

    /* End of Saturate: '<S1>/Saturation1' */
  }

  {
    real_T denAccum;

    /* Update for DiscreteTransferFcn: '<S1>/Discrete Transfer Fcn1' */
    denAccum = sim_B.ValveOD;
    denAccum -= sim_P.DiscreteTransferFcn1_DenCoef[1] *
      sim_DW.DiscreteTransferFcn1_states;
    denAccum /= sim_P.DiscreteTransferFcn1_DenCoef[0];
    sim_DW.DiscreteTransferFcn1_states = denAccum;

    /* Update for Atomic SubSystem: '<S1>/PID' */
    /* Update for DiscreteIntegrator: '<S2>/Discrete-Time Integrator' */
    sim_DW.DiscreteTimeIntegrator_DSTATE += sim_P.DiscreteTimeIntegrator_gainval
      * sim_B.Ki;

    /* Update for UnitDelay: '<S3>/UD' */
    sim_DW.UD_DSTATE = sim_B.TSamp;

    /* End of Update for SubSystem: '<S1>/PID' */
  }
}

/* Model initialize function */
void sim_initialize(void)
{
  /* Registration code */

  /* initialize real-time model */
  (void) memset((void *)sim_M, 0,
                sizeof(RT_MODEL_sim_T));

  /* Set task counter limit used by the static main program */
  (sim_M)->Timing.TaskCounters.cLimit[0] = 1;
  (sim_M)->Timing.TaskCounters.cLimit[1] = 1;
  (sim_M)->Timing.TaskCounters.cLimit[2] = 2;

  {
    /* Setup solver object */
    rtsiSetSimTimeStepPtr(&sim_M->solverInfo, &sim_M->Timing.simTimeStep);
    rtsiSetTPtr(&sim_M->solverInfo, &rtmGetTPtr(sim_M));
    rtsiSetStepSizePtr(&sim_M->solverInfo, &sim_M->Timing.stepSize0);
    rtsiSetErrorStatusPtr(&sim_M->solverInfo, (&rtmGetErrorStatus(sim_M)));
    rtsiSetRTModelPtr(&sim_M->solverInfo, sim_M);
  }

  rtsiSetSimTimeStep(&sim_M->solverInfo, MAJOR_TIME_STEP);
  rtsiSetIsMinorTimeStepWithModeChange(&sim_M->solverInfo, false);
  rtsiSetIsContModeFrozen(&sim_M->solverInfo, false);
  rtsiSetSolverName(&sim_M->solverInfo,"FixedStepDiscrete");
  rtmSetTPtr(sim_M, &sim_M->Timing.tArray[0]);
  rtmSetTFinal(sim_M, 150.0);
  sim_M->Timing.stepSize0 = 0.01;

  /* Setup for data logging */
  {
    static RTWLogInfo rt_DataLoggingInfo;
    rt_DataLoggingInfo.loggingInterval = (NULL);
    sim_M->rtwLogInfo = &rt_DataLoggingInfo;
  }

  /* Setup for data logging */
  {
    /*
     * Set pointers to the data and signal info each state
     */
    {
      static int_T rt_LoggedStateWidths[] = {
        1,
        1,
        1
      };

      static int_T rt_LoggedStateNumDimensions[] = {
        1,
        1,
        1
      };

      static int_T rt_LoggedStateDimensions[] = {
        1,
        1,
        1
      };

      static boolean_T rt_LoggedStateIsVarDims[] = {
        0,
        0,
        0
      };

      static BuiltInDTypeId rt_LoggedStateDataTypeIds[] = {
        SS_DOUBLE,
        SS_DOUBLE,
        SS_DOUBLE
      };

      static int_T rt_LoggedStateComplexSignals[] = {
        0,
        0,
        0
      };

      static RTWPreprocessingFcnPtr rt_LoggingStatePreprocessingFcnPtrs[] = {
        (NULL),
        (NULL),
        (NULL)
      };

      static const char_T *rt_LoggedStateLabels[] = {
        "states",
        "DSTATE",
        "DSTATE"
      };

      static const char_T *rt_LoggedStateBlockNames[] = {
        "sim/Model/Discrete\nTransfer Fcn1",
        "sim/Model/PID/Discrete-Time\nIntegrator",
        "sim/Model/PID/Discrete Derivative/UD"
      };

      static const char_T *rt_LoggedStateNames[] = {
        "",
        "",
        ""
      };

      static boolean_T rt_LoggedStateCrossMdlRef[] = {
        0,
        0,
        0
      };

      static RTWLogDataTypeConvert rt_RTWLogDataTypeConvert[] = {
        { 0, SS_DOUBLE, SS_DOUBLE, 0, 0, 0, 1.0, 0, 0.0 },

        { 0, SS_DOUBLE, SS_DOUBLE, 0, 0, 0, 1.0, 0, 0.0 },

        { 0, SS_DOUBLE, SS_DOUBLE, 0, 0, 0, 1.0, 0, 0.0 }
      };

      static RTWLogSignalInfo rt_LoggedStateSignalInfo = {
        3,
        rt_LoggedStateWidths,
        rt_LoggedStateNumDimensions,
        rt_LoggedStateDimensions,
        rt_LoggedStateIsVarDims,
        (NULL),
        (NULL),
        rt_LoggedStateDataTypeIds,
        rt_LoggedStateComplexSignals,
        (NULL),
        rt_LoggingStatePreprocessingFcnPtrs,

        { rt_LoggedStateLabels },
        (NULL),
        (NULL),
        (NULL),

        { rt_LoggedStateBlockNames },

        { rt_LoggedStateNames },
        rt_LoggedStateCrossMdlRef,
        rt_RTWLogDataTypeConvert
      };

      static void * rt_LoggedStateSignalPtrs[3];
      rtliSetLogXSignalPtrs(sim_M->rtwLogInfo, (LogSignalPtrsType)
                            rt_LoggedStateSignalPtrs);
      rtliSetLogXSignalInfo(sim_M->rtwLogInfo, &rt_LoggedStateSignalInfo);
      rt_LoggedStateSignalPtrs[0] = (void*)&sim_DW.DiscreteTransferFcn1_states;
      rt_LoggedStateSignalPtrs[1] = (void*)&sim_DW.DiscreteTimeIntegrator_DSTATE;
      rt_LoggedStateSignalPtrs[2] = (void*)&sim_DW.UD_DSTATE;
    }

    rtliSetLogT(sim_M->rtwLogInfo, "tout");
    rtliSetLogX(sim_M->rtwLogInfo, "xout");
    rtliSetLogXFinal(sim_M->rtwLogInfo, "");
    rtliSetLogVarNameModifier(sim_M->rtwLogInfo, "rt_");
    rtliSetLogFormat(sim_M->rtwLogInfo, 0);
    rtliSetLogMaxRows(sim_M->rtwLogInfo, 0);
    rtliSetLogDecimation(sim_M->rtwLogInfo, 1);
    rtliSetLogY(sim_M->rtwLogInfo, "");
    rtliSetLogYSignalInfo(sim_M->rtwLogInfo, (NULL));
    rtliSetLogYSignalPtrs(sim_M->rtwLogInfo, (NULL));
  }

  /* block I/O */
  {
    sim_B.Step = 0.0;
    sim_B.TmpRTBAtPIDInport1 = 0.0;
    sim_B.y = 0.0;
    sim_B.ValveOD = 0.0;
    sim_B.ZeroOrderHold2 = 0.0;
    sim_B.u = 0.0;
    sim_B.e = 0.0;
    sim_B.Kp = 0.0;
    sim_B.DiscreteTimeIntegrator = 0.0;
    sim_B.kd = 0.0;
    sim_B.TSamp = 0.0;
    sim_B.Uk1 = 0.0;
    sim_B.Diff = 0.0;
    sim_B.Sum1 = 0.0;
    sim_B.u_h = 0.0;
    sim_B.Ki = 0.0;
  }

  /* states (dwork) */
  (void) memset((void *)&sim_DW, 0,
                sizeof(DW_sim_T));
  sim_DW.DiscreteTransferFcn1_states = 0.0;
  sim_DW.DiscreteTimeIntegrator_DSTATE = 0.0;
  sim_DW.UD_DSTATE = 0.0;
  sim_DW.TmpRTBAtPIDInport1_Buf0 = 0.0;
  sim_DW.TmpRTBAtPIDInport1_Buf1 = 0.0;
  sim_DW.TmpRTBAtPIDInport1_Buf2 = 0.0;

  /* Matfile logging */
  rt_StartDataLoggingWithStartTime(sim_M->rtwLogInfo, 0.0, rtmGetTFinal(sim_M),
    sim_M->Timing.stepSize0, (&rtmGetErrorStatus(sim_M)));

  /* Start for RateTransition generated from: '<S1>/PID' */
  sim_B.TmpRTBAtPIDInport1 = sim_P.TmpRTBAtPIDInport1_InitialCondi;

  /* Start for RateTransition generated from: '<S1>/PID' */
  rtw_win_mutex_create(&sim_DW.TmpRTBAtPIDInport1_d0_SEMAPHORE);

  /* InitializeConditions for RateTransition generated from: '<S1>/PID' */
  sim_DW.TmpRTBAtPIDInport1_Buf0 = sim_P.TmpRTBAtPIDInport1_InitialCondi;

  /* InitializeConditions for DiscreteTransferFcn: '<S1>/Discrete Transfer Fcn1' */
  sim_DW.DiscreteTransferFcn1_states = sim_P.DiscreteTransferFcn1_InitialSta;

  /* SystemInitialize for Atomic SubSystem: '<S1>/PID' */
  /* InitializeConditions for DiscreteIntegrator: '<S2>/Discrete-Time Integrator' */
  sim_DW.DiscreteTimeIntegrator_DSTATE = sim_P.DiscreteTimeIntegrator_IC;

  /* InitializeConditions for UnitDelay: '<S3>/UD' */
  sim_DW.UD_DSTATE = sim_P.DiscreteDerivative_ICPrevScaled;

  /* End of SystemInitialize for SubSystem: '<S1>/PID' */
}

/* Model terminate function */
void sim_terminate(void)
{
  /* Terminate for RateTransition generated from: '<S1>/PID' */
  rtw_win_mutex_close(sim_DW.TmpRTBAtPIDInport1_d0_SEMAPHORE);
}
