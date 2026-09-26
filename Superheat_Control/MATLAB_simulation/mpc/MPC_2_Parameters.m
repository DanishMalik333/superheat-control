clc; close all; clear;

%% Plant — rediscretized from Ts=0.01s to Ts=0.02s (ALSmart cycle)
Ts_orig = 0.01;
Ts      = 0.2;   % MPC runs at ALSmart slow-task period

num = 0.03572;
den = [1  -0.998214];

sys_orig = tf(num, den, Ts_orig);   % original discrete plant at 0.01s
sys      = d2d(sys_orig, Ts);       % rediscretize to 0.02s

%% Step response

N = 30/Ts;   
P = 50; 
M = 2;  

y_step = step(sys, (0:N)*Ts);
% y_step = y_step / y_step(end); 
% Match original variable names exactly
S_new  = y_step';
SS     = S_new;
t      = (0:N)*Ts;

%% Matrices — same variable names as original
G = toeplitz(SS(2:P+1)', [SS(2)        zeros(1,M-1)]);
H = hankel(SS(3:P+2)',   [SS(P+2:N)    zeros(1,P-1)]);

%% Bryson's Rule
% Define max acceptable deviations
max_y_error = 1;   % max output error (5% of normalized range)
max_du      = 0.1;      

% Raw Bryson weights
Q_raw = (1/max_y_error^2) * eye(P);
R_raw = (1/max_du^2)      * eye(M);

% Normalize so Q diagonal = 1, preserving Q/R ratio
Q = eye(P);
R = (max_y_error^2 / max_du^2) * eye(M);

fprintf('=== Bryson Weights ===\n')
fprintf('max_y_error = %.3f\n', max_y_error)
fprintf('max_du      = %.3f\n', max_du)
fprintf('Q diagonal  = 1.0 (normalized)\n')
fprintf('R diagonal  = %.6f\n', max_y_error^2/max_du^2)

%% Gain
K_full = (G'*Q*G + R) \ (G'*Q);
K1     = K_full(1,:);       % 1xP

%% Steady state
SS_N1   = SS(N+1);
SS_vals = SS(2:N+1);

%% Sanity checks
fprintf('\n=== Dimensions ===\n')
fprintf('N=%d, P=%d, M=%d\n', N, P, M)
fprintf('G:  %dx%d\n', size(G))
fprintf('H:  %dx%d\n', size(H))
fprintf('K1: %dx%d\n', size(K1))
fprintf('Condition number: %.2f\n', cond(G'*Q*G + R))
fprintf('SS_N1 = %.4f\n', SS_N1)
fprintf('K1 max: %.6f\n', max(abs(K1)))
fprintf('K1 min: %.6f\n', min(abs(K1)))