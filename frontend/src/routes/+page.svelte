<script lang="ts">
	import { onMount } from 'svelte';
	import * as THREE from 'three';

	// Constants
	let maxMoments = $derived.by(() => {
		if (circuitState.length === 0) return 4;
		const maxUsed = circuitState.reduce((max, op) => Math.max(max, op.time), -1);
		return Math.max(4, maxUsed + 2);
	});
	
	const STANDARD_GATE_GROUPS = [
		{
			name: 'Single-Qubit',
			colorClass: 'pauli-gate',
			gates: [
				{ type: 'X', name: 'Pauli-X', description: 'Quantum NOT gate' },
				{ type: 'Y', name: 'Pauli-Y', description: 'Pauli-Y rotation' },
				{ type: 'Z', name: 'Pauli-Z', description: 'Pauli-Z rotation' },
				{ type: 'H', name: 'Hadamard', description: 'Creates superposition' },
				{ type: 'S', name: 'Phase S', description: 'Phase rotation of pi/2' },
				{ type: 'T', name: 'Phase T', description: 'Phase rotation of pi/4' }
			]
		},
		{
			name: 'Multi-Qubit',
			colorClass: 'multi-gate',
			gates: [
				{ type: 'CX', name: 'CNOT', description: 'Controlled-NOT' },
				{ type: 'CZ', name: 'CZ', description: 'Controlled-Phase' },
				{ type: 'SWAP', name: 'SWAP', description: 'Swap two qubits' },
				{ type: 'CCX', name: 'Toffoli', description: 'Double-controlled NOT' }
			]
		},
		{
			name: 'Native/Parametric',
			colorClass: 'parametric-gate',
			gates: [
				{ type: 'RX', name: 'RX', description: 'Rotate around X axis' },
				{ type: 'RY', name: 'RY', description: 'Rotate around Y axis' },
				{ type: 'RZ', name: 'RZ', description: 'Rotate around Z axis' }
			]
		},
		{
			name: 'Operations',
			colorClass: 'classical-gate',
			gates: [
				{ type: 'M', name: 'Measure', description: 'Measure qubit state' },
				{ type: 'Reset', name: 'Reset', description: 'Reset qubit to |0>' }
			]
		}
	];

	const GOOGLE_HARDWARE_GATE_GROUPS = [
		{
			name: 'Single-Qubit (Native)',
			colorClass: 'pauli-gate',
			gates: [
				{ type: 'PhasedXZ', name: 'PhasedXZ', description: 'Google Phased X-Z rotation' },
				{ type: 'XPow', name: 'XPow', description: 'Google X-Power gate' },
				{ type: 'Z', name: 'Pauli-Z', description: 'Pauli-Z rotation' }
			]
		},
		{
			name: 'Multi-Qubit (Native)',
			colorClass: 'multi-gate',
			gates: [
				{ type: 'FSim', name: 'FSim', description: 'Fermi-Hubbard simulation gate' },
				{ type: 'CZ', name: 'CZ', description: 'Controlled-Phase' }
			]
		},
		{
			name: 'Operations',
			colorClass: 'classical-gate',
			gates: [
				{ type: 'M', name: 'Measure', description: 'Measure qubit state' },
				{ type: 'Reset', name: 'Reset', description: 'Reset qubit to |0>' }
			]
		}
	];

	let gridRows = $state(2);
	let gridCols = $state(3);

	let gridQubits = $derived.by(() => {
		const list = [];
		for (let r = 0; r < gridRows; r++) {
			for (let c = 0; c < gridCols; c++) {
				list.push({
					name: `q(${r},${c})`,
					row: r,
					col: c,
					index: r * 10 + c
				});
			}
		}
		return list;
	});

	// --- App State ---
	interface CircuitOp {
		id: string;
		gate: string;
		target?: number;
		control?: number;
		controls?: number[];
		targets?: number[];
		time: number;
		param?: string;
	}

	let workspaceMode = $state('normal'); // 'normal' or 'research'
	let topology = $state('line'); // 'line' or 'grid'
	let gateSet = $state('standard'); // 'standard' or 'native'
	
	let circuitState = $state<CircuitOp[]>([]);
	let lineQubits = $state([
		{ name: 'q[0]', row: 4, col: 4, index: 0 },
		{ name: 'q[1]', row: 4, col: 5, index: 1 }
	]);
	
	let theme = $state('dark'); // dark mode by default
	let activeTab = $state('histogram'); // histogram, qsphere, coupling_map
	let compilationPreview = $state(false); // compilation transpile preview toggle

	// Collapsible states
	let rightCollapsed = $state(false);
	let bottomCollapsed = $state(false);

	// Drag & Drop
	let draggedGateType = $state<string | null>(null);
	let draggedOpId = $state<string | null>(null);
	let dragOverCell = $state<{ moment: number; qubit: number } | null>(null);

	// Context Menu
	let editingOp = $state<CircuitOp | null>(null);
	let contextMenuPos = $state<{ x: number; y: number } | null>(null);

	// Simulation configs
	let normalBackend = $state('standard_sim');
	let researchBackend = $state('ideal_qsim');
	let repetitions = $state(1000);
	
	// Noise models
	let thermalNoise = $state(false);
	let depolarizingNoise = $state(false);
	let noiseProbability = $state(0.02);
	let returnStateVector = $state(true);

	// API & Job Pipeline
	let gatewayHealth = $state<'checking' | 'online' | 'offline'>('checking');
	let activeJobId = $state<string | null>(null);
	let jobStatus = $state<string | null>(null);
	let jobError = $state<string | null>(null);
	let isRunning = $state(false);

	// Simulation Results
	let simulationResults = $state<{
		backend: string;
		depth: number;
		results: Record<string, number>;
		state_vector?: number[];
	} | null>(null);

	// Active Qubits List
	let activeQubits = $derived.by(() => {
		if (workspaceMode === 'normal') {
			return lineQubits;
		}
		return topology === 'line' ? lineQubits : gridQubits;
	});

	// Dynamic Gate Groups
	let gateGroups = $derived.by(() => {
		if (workspaceMode === 'normal' || gateSet === 'standard') {
			return STANDARD_GATE_GROUPS;
		}
		return GOOGLE_HARDWARE_GATE_GROUPS;
	});

	// Adjacency check for couplings on the Grid
	function areQubitsAdjacent(q1: number, q2: number): boolean {
		if (topology === 'line') {
			return Math.abs(q1 - q2) === 1;
		}
		// grid topology: indices are row * 10 + col
		const r1 = Math.floor(q1 / 10), c1 = q1 % 10;
		const r2 = Math.floor(q2 / 10), c2 = q2 % 10;
		return Math.abs(r1 - r2) + Math.abs(c1 - c2) === 1;
	}

	function checkCouplingViolation(op: CircuitOp): boolean {
		if (workspaceMode !== 'research' || topology !== 'grid') return false;
		if (op.gate === 'CX' || op.gate === 'CZ' || op.gate === 'FSim') {
			if (op.control !== undefined && op.target !== undefined) {
				return !areQubitsAdjacent(op.control, op.target);
			}
		} else if (op.gate === 'SWAP') {
			if (op.targets && op.targets.length >= 2) {
				return !areQubitsAdjacent(op.targets[0], op.targets[1]);
			}
		} else if (op.gate === 'CCX') {
			if (op.controls && op.controls.length >= 2 && op.target !== undefined) {
				const adj1 = areQubitsAdjacent(op.controls[0], op.target);
				const adj2 = areQubitsAdjacent(op.controls[1], op.target);
				return !adj1 && !adj2;
			}
		}
		return false;
	}

	function isCouplingActive(q1: number, q2: number): boolean {
		return circuitState.some(op => {
			if (['CX', 'CZ', 'FSim'].includes(op.gate)) {
				return (op.control === q1 && op.target === q2) || (op.control === q2 && op.target === q1);
			}
			if (op.gate === 'SWAP') {
				return op.targets && op.targets.includes(q1) && op.targets.includes(q2);
			}
			if (op.gate === 'CCX') {
				if (op.controls && op.controls.length >= 2 && op.target !== undefined) {
					const isC1T = (op.controls[0] === q1 && op.target === q2) || (op.controls[0] === q2 && op.target === q1);
					const isC2T = (op.controls[1] === q1 && op.target === q2) || (op.controls[1] === q2 && op.target === q1);
					return isC1T || isC2T;
				}
			}
			return false;
		});
	}

	// Calculate single qubit probability of $|1\rangle$ (Heatmap rendering)
	function getQubitProbability1(qubitIdx: number): number {
		if (!simulationResults || !simulationResults.results) return 0;
		let matchingCount = 0;
		let totalCount = 0;

		const qubitPos = activeQubits.findIndex(q => q.index === qubitIdx);
		if (qubitPos === -1) return 0;

		Object.entries(simulationResults.results).forEach(([state, count]) => {
			totalCount += count;
			const cleanState = state.replace(/[|⟩]/g, '');
			if (cleanState.charAt(qubitPos) === '1') {
				matchingCount += count;
			}
		});

		return totalCount > 0 ? matchingCount / totalCount : 0;
	}

	// Cirq Python Code Exporter
	let cirqCode = $derived.by(() => {
		const qName = (idx: number) => {
			if (workspaceMode === 'normal' || topology === 'line') {
				return `qubits[${idx}]`;
			}
			const pos = activeQubits.findIndex(q => q.index === idx);
			return `qubits[${pos !== -1 ? pos : 0}]`;
		};

		let code = `import cirq\n\n`;
		code += `# Initialize qubits\n`;
		if (workspaceMode === 'normal' || topology === 'line') {
			code += `qubits = cirq.LineQubit.range(${activeQubits.length})\n`;
		} else {
			code += `qubits = [\n`;
			activeQubits.forEach((q, idx) => {
				code += `    cirq.GridQubit(${q.row}, ${q.col}), # qubits[${idx}] is q(${q.row},${q.col})\n`;
			});
			code += `]\n`;
		}
		
		code += `\n# Build circuit\n`;
		code += `circuit = cirq.Circuit()\n\n`;

		const processedCX = new Set<string>();
		const sortedState = [...circuitState].sort((a, b) => a.time - b.time);

		sortedState.forEach(op => {
			const qArg = qName(op.target!);

			if (['H', 'X', 'Y', 'Z', 'S', 'T', 'Reset'].includes(op.gate)) {
				let gName = op.gate;
				if (gName === 'Reset') gName = 'reset';
				code += `circuit.append(cirq.${gName}(${qArg}))\n`;
			} else if (['RX', 'RY', 'RZ'].includes(op.gate)) {
				let rad = '0.0';
				if (op.param) {
					if (op.param === 'pi/2' || op.param === 'π/2') rad = '3.14159 / 2';
					else if (op.param === 'pi/4' || op.param === 'π/4') rad = '3.14159 / 4';
					else if (op.param === 'pi' || op.param === 'π') rad = '3.14159';
					else rad = op.param;
				}
				code += `circuit.append(cirq.${op.gate.toLowerCase()}(rad=${rad})(${qArg}))\n`;
			} else if (op.gate === 'CX' || op.gate === 'CZ' || op.gate === 'FSim') {
				const cIdx = op.control;
				const tIdx = op.target;
				if (cIdx !== undefined && tIdx !== undefined) {
					const key = `${op.time}_${cIdx}_${tIdx}`;
					if (!processedCX.has(key)) {
						let gName = op.gate;
						if (gName === 'CX') gName = 'CNOT';
						let gateExpr = `cirq.${gName}`;
						if (gName === 'FSim') gateExpr = `cirq.FSimGate(theta=0.5, phi=0.2)`;
						
						code += `circuit.append(${gateExpr}(${qName(cIdx)}, ${qName(tIdx)}))\n`;
						processedCX.add(key);
					}
				}
			} else if (op.gate === 'SWAP') {
				if (op.targets && op.targets.length >= 2) {
					const key = `${op.time}_swap_${op.targets[0]}_${op.targets[1]}`;
					if (!processedCX.has(key)) {
						code += `circuit.append(cirq.SWAP(${qName(op.targets[0])}, ${qName(op.targets[1])}))\n`;
						processedCX.add(key);
					}
				}
			} else if (op.gate === 'CCX') {
				if (op.controls && op.controls.length >= 2 && op.target !== undefined) {
					const key = `${op.time}_ccx_${op.controls[0]}_${op.controls[1]}_${op.target}`;
					if (!processedCX.has(key)) {
						code += `circuit.append(cirq.TOFFOLI(${qName(op.controls[0])}, ${qName(op.controls[1])}, ${qName(op.target)}))\n`;
						processedCX.add(key);
					}
				}
			} else if (op.gate === 'PhasedXZ') {
				code += `circuit.append(cirq.PhasedXZGate(x_exponent=0.5, z_exponent=0.2, axis_phase_exponent=0.0)(${qArg}))\n`;
			} else if (op.gate === 'XPow') {
				code += `circuit.append(cirq.XPowGate(exponent=0.5)(${qArg}))\n`;
			} else if (op.gate === 'M') {
				code += `circuit.append(cirq.measure(${qArg}, key='m_${op.target}'))\n`;
			}
		});

		if (compilationPreview && workspaceMode === 'research') {
			code += `\n# Compilation preview optimized for Google Sycamore target gateset\n`;
			code += `gateset = cirq.google.SycamoreTargetGateset()\n`;
			code += `compiled_circuit = cirq.optimize_for_target_gateset(circuit, gateset=gateset)\n`;
			code += `print("Compiled Circuit:")\n`;
			code += `print(compiled_circuit)\n`;
		} else {
			code += `\nprint("Abstract Circuit:")\n`;
			code += `print(circuit)\n`;
		}

		return code;
	});

	let highlightedCode = $derived(highlightCodeSyntax(cirqCode));

	// THREE is imported from npm package 'three'

	function checkGatewayHealth() {
		fetch('http://localhost:8080/health')
			.then(res => {
				if (res.ok) {
					gatewayHealth = 'online';
				} else {
					gatewayHealth = 'offline';
				}
			})
			.catch(() => {
				gatewayHealth = 'offline';
			});
	}

	function getStatesWithHammingWeight(numQubits: number, weight: number): number[] {
		const states: number[] = [];
		const totalStates = 1 << numQubits;
		for (let i = 0; i < totalStates; i++) {
			let count = 0;
			let temp = i;
			while (temp > 0) {
				if (temp & 1) count++;
				temp >>= 1;
			}
			if (count === weight) {
				states.push(i);
			}
		}
		return states;
	}

	function parseParamToRad(param: string | undefined): number {
		if (!param) return 0;
		const clean = param.toLowerCase().trim();
		if (clean === 'pi/2' || clean === 'π/2') return Math.PI / 2;
		if (clean === 'pi/4' || clean === 'π/4') return Math.PI / 4;
		if (clean === 'pi' || clean === 'π') return Math.PI;
		const parsed = parseFloat(clean);
		return isNaN(parsed) ? 0 : parsed;
	}

	function serializeQubit(qubitIndex: number) {
		const qObj = activeQubits.find(q => q.index === qubitIndex);
		if (!qObj) {
			return {
				cirq_type: "GridQubit",
				row: 4,
				col: 4 + qubitIndex
			};
		}
		return {
			cirq_type: "GridQubit",
			row: qObj.row,
			col: qObj.col
		};
	}

	function compileStateToCirqJson(): string {
		const momentsList: any[] = [];

		for (let m = 0; m < maxMoments; m++) {
			const opsAtMoment = circuitState.filter(op => op.time === m);
			if (opsAtMoment.length === 0) {
				momentsList.push({
					cirq_type: "Moment",
					operations: []
				});
				continue;
			}

			const serializedOps: any[] = [];
			const processedOpIds = new Set<string>();

			opsAtMoment.forEach(op => {
				if (processedOpIds.has(op.id)) return;

				let gateObj: any = null;
				let qubitsObj: any[] = [];

				if (op.gate === 'H') {
					gateObj = { cirq_type: "HPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'X') {
					gateObj = { cirq_type: "XPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'Y') {
					gateObj = { cirq_type: "YPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'Z') {
					gateObj = { cirq_type: "ZPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'S') {
					gateObj = { cirq_type: "ZPowGate", exponent: 0.5, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'T') {
					gateObj = { cirq_type: "ZPowGate", exponent: 0.25, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'RX') {
					const exponent = parseParamToRad(op.param) / Math.PI;
					gateObj = { cirq_type: "XPowGate", exponent, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'RY') {
					const exponent = parseParamToRad(op.param) / Math.PI;
					gateObj = { cirq_type: "YPowGate", exponent, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'RZ') {
					const exponent = parseParamToRad(op.param) / Math.PI;
					gateObj = { cirq_type: "ZPowGate", exponent, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'CX') {
					gateObj = { cirq_type: "CXPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.control!), serializeQubit(op.target!)];
					processedOpIds.add(op.id);
				} else if (op.gate === 'CZ') {
					gateObj = { cirq_type: "CZPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.control!), serializeQubit(op.target!)];
					processedOpIds.add(op.id);
				} else if (op.gate === 'SWAP') {
					gateObj = { cirq_type: "SwapPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.targets![0]), serializeQubit(op.targets![1])];
					processedOpIds.add(op.id);
				} else if (op.gate === 'CCX') {
					gateObj = { cirq_type: "CCXPowGate", exponent: 1.0, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.controls![0]), serializeQubit(op.controls![1]), serializeQubit(op.target!)];
					processedOpIds.add(op.id);
				} else if (op.gate === 'PhasedXZ') {
					gateObj = { cirq_type: "PhasedXZGate", x_exponent: 0.5, z_exponent: 0.2, axis_phase_exponent: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'XPow') {
					gateObj = { cirq_type: "XPowGate", exponent: 0.5, global_shift: 0.0 };
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'FSim') {
					gateObj = { cirq_type: "FSimGate", theta: 0.5, phi: 0.2 };
					qubitsObj = [serializeQubit(op.control!), serializeQubit(op.target!)];
					processedOpIds.add(op.id);
				} else if (op.gate === 'M') {
					gateObj = {
						cirq_type: "MeasurementGate",
						num_qubits: 1,
						key: `m_${op.target}`,
						invert_mask: []
					};
					qubitsObj = [serializeQubit(op.target!)];
				} else if (op.gate === 'Reset') {
					gateObj = { cirq_type: "ResetChannel", dimension: 2 };
					qubitsObj = [serializeQubit(op.target!)];
				}

				if (gateObj && qubitsObj.length > 0) {
					serializedOps.push({
						cirq_type: "GateOperation",
						gate: gateObj,
						qubits: qubitsObj
					});
				}
			});

			momentsList.push({
				cirq_type: "Moment",
				operations: serializedOps
			});
		}

		return JSON.stringify({
			cirq_type: "Circuit",
			moments: momentsList
		});
	}

	function clearCircuit() {
		circuitState = [];
		simulationResults = null;
		activeJobId = null;
		jobStatus = null;
		jobError = null;
	}

	function formatStateLabelBinary(state: string, numQubits: number): string {
		const padded = state.padStart(numQubits, '0');
		return `|${padded}⟩`;
	}

	let totalHistogramCount = $derived.by(() => {
		if (!simulationResults || !simulationResults.results) return 1;
		return Object.values(simulationResults.results).reduce((sum, count) => sum + count, 0);
	});

	interface StatevectorDetail {
		state: string;
		real: number;
		imag: number;
		amp: number;
		phase: number;
	}

	let stateVectorDetails = $derived.by<StatevectorDetail[]>(() => {
		if (!simulationResults || !simulationResults.state_vector) return [];
		const sv = simulationResults.state_vector;
		const numQubits = activeQubits.length;
		const totalStates = 1 << numQubits;
		const list: StatevectorDetail[] = [];

		for (let i = 0; i < totalStates; i++) {
			const r = sv[i * 2] || 0;
			const img = sv[i * 2 + 1] || 0;
			const amp = Math.sqrt(r * r + img * img);
			let phaseRad = Math.atan2(img, r);
			let phaseDeg = (phaseRad * 180) / Math.PI;
			if (phaseDeg < 0) phaseDeg += 360;

			const binStr = i.toString(2).padStart(numQubits, '0');
			list.push({
				state: binStr,
				real: r,
				imag: img,
				amp,
				phase: phaseDeg
			});
		}
		return list;
	});

	// --- Lifecycle ---
	onMount(() => {
		checkGatewayHealth();

		// Default initial circuit (Bell State)
		circuitState = [
			{ id: Math.random().toString(), gate: 'H', target: 0, time: 0 },
			{ id: Math.random().toString(), gate: 'CX', control: 0, target: 1, time: 1 },
			{ id: Math.random().toString(), gate: 'M', target: 0, time: 2 },
			{ id: Math.random().toString(), gate: 'M', target: 1, time: 2 }
		];

		// Mock pre-completed simulation payload
		activeJobId = "6c6da121-88ad-4be6-b398-ba355788e4a3";
		jobStatus = "COMPLETED";
		simulationResults = {
			backend: "generic",
			depth: 3,
			results: {
				"00": 509,
				"11": 491
			},
			state_vector: [0.70710678, 0, 0, 0, 0, 0, 0.70710678, 0]
		};

	});

	// Trigger simulation on state change
	let debounceTimeout: number;
	$effect(() => {
		// Watch state changes
		const _ = circuitState.length;
		const __ = circuitState.map(o => `${o.gate}_${o.time}_${o.target}_${o.param}`);
		const mode = workspaceMode;
		const topo = topology;

		clearTimeout(debounceTimeout);
		debounceTimeout = setTimeout(() => {
			if (circuitState.length > 0) {
				autoRunSimulation();
			} else {
				simulationResults = null;
			}
		}, 300) as any;
	});

	// Svelte 5 effects for Three.js Q-sphere lifecycle
	$effect(() => {
		if (activeTab === 'qsphere' && qsphereContainer) {
			initThreeQSphere(qsphereContainer);
			return () => {
				cleanupThreeQSphere();
			};
		}
	});

	$effect(() => {
		if (simulationResults && simulationResults.state_vector) {
			updateQSphere(simulationResults.state_vector);
		} else {
			if (activeTab === 'qsphere') {
				updateQSphere([]);
			}
		}
	});

	// Mode/Topology tab auto-adjust watcher
	$effect(() => {
		if (workspaceMode === 'research') {
			if (topology === 'grid' && activeTab === 'qsphere') {
				activeTab = 'coupling_map';
			} else if (topology === 'line' && activeTab === 'coupling_map') {
				activeTab = 'qsphere';
			}
		}
	});

	// Mode switch watcher
	$effect(() => {
		if (workspaceMode === 'normal') {
			topology = 'line';
			activeTab = 'histogram';
			// Restrict normal mode to 2-5 qubits
			if (lineQubits.length > 5) {
				lineQubits = lineQubits.slice(0, 5);
			}
		}
	});

	// --- Canvas Methods ---
	function addQubit() {
		const max = workspaceMode === 'normal' ? 5 : 10;
		if (lineQubits.length >= max) {
			alert(`Maximum ${max} qubits allowed in ${workspaceMode} mode.`);
			return;
		}
		const idx = lineQubits.length;
		lineQubits.push({
			name: `q[${idx}]`,
			row: 4,
			col: 4 + idx,
			index: idx
		});
	}

	function removeQubit() {
		if (lineQubits.length <= 1) return;
		const idx = lineQubits.length - 1;
		circuitState = circuitState.filter(op => {
			if (op.target === idx || op.control === idx) return false;
			if (op.targets?.includes(idx) || op.controls?.includes(idx)) return false;
			return true;
		});
		lineQubits.pop();
	}

	function removeGridRow() {
		if (gridRows <= 1) return;
		const targetRow = gridRows - 1;
		circuitState = circuitState.filter(op => {
			const isAffected = (q: number) => Math.floor(q / 10) === targetRow;
			if (op.target !== undefined && isAffected(op.target)) return false;
			if (op.control !== undefined && isAffected(op.control)) return false;
			if (op.targets && op.targets.some(isAffected)) return false;
			if (op.controls && op.controls.some(isAffected)) return false;
			return true;
		});
		gridRows--;
	}

	function removeGridCol() {
		if (gridCols <= 1) return;
		const targetCol = gridCols - 1;
		circuitState = circuitState.filter(op => {
			const isAffected = (q: number) => (q % 10) === targetCol;
			if (op.target !== undefined && isAffected(op.target)) return false;
			if (op.control !== undefined && isAffected(op.control)) return false;
			if (op.targets && op.targets.some(isAffected)) return false;
			if (op.controls && op.controls.some(isAffected)) return false;
			return true;
		});
		gridCols--;
	}

	function getCellGate(time: number, qubitIdx: number) {
		return circuitState.find(op => {
			if (op.time !== time) return false;
			if (op.target === qubitIdx) return true;
			if (op.control === qubitIdx) return true;
			if (op.targets?.includes(qubitIdx)) return true;
			if (op.controls?.includes(qubitIdx)) return true;
			return false;
		});
	}

	function handlePaletteDragStart(event: DragEvent, gateType: string) {
		draggedGateType = gateType;
		draggedOpId = null;
		if (event.dataTransfer) {
			event.dataTransfer.setData('text/plain', gateType);
			event.dataTransfer.effectAllowed = 'copy';
		}
	}

	function handleCanvasDragStart(event: DragEvent, opId: string) {
		const op = circuitState.find(o => o.id === opId);
		if (!op) return;
		draggedGateType = op.gate;
		draggedOpId = opId;
		if (event.dataTransfer) {
			event.dataTransfer.setData('text/plain', op.gate);
			event.dataTransfer.effectAllowed = 'move';
		}
	}

	function handleDragOver(event: DragEvent) {
		event.preventDefault();
	}

	function handleCanvasDrop(event: DragEvent, moment: number, qubit: number) {
		event.preventDefault();
		const gateType = event.dataTransfer?.getData('text/plain') || draggedGateType;
		if (!gateType) return;

		// Clear any existing gates at this time step on affected qubits
		const affectedQubits = getAffectedQubits(gateType, qubit);
		circuitState = circuitState.filter(op => {
			if (op.time !== moment) return true;
			if (op.id === draggedOpId) return true; // Keep moving op
			return !affectedQubits.includes(op.target!) && 
			       !affectedQubits.includes(op.control!) &&
			       !op.targets?.some(q => affectedQubits.includes(q)) &&
			       !op.controls?.some(q => affectedQubits.includes(q));
		});

		if (draggedOpId) {
			circuitState = circuitState.map(op => {
				if (op.id === draggedOpId) {
					const updated = { ...op, time: moment };
					if (['H', 'X', 'Y', 'Z', 'S', 'T', 'M', 'Reset', 'PhasedXZ', 'XPow'].includes(op.gate)) {
						updated.target = qubit;
					} else if (['RX', 'RY', 'RZ'].includes(op.gate)) {
						updated.target = qubit;
					} else if (op.gate === 'CX' || op.gate === 'CZ' || op.gate === 'FSim') {
						updated.control = qubit;
						updated.target = qubit + 1 < activeQubits.length ? qubit + 1 : qubit - 1;
					} else if (op.gate === 'SWAP') {
						const q2 = qubit + 1 < activeQubits.length ? qubit + 1 : qubit - 1;
						updated.targets = [qubit, q2];
					} else if (op.gate === 'CCX') {
						const q2 = qubit + 1 < activeQubits.length ? qubit + 1 : qubit - 1;
						const q3 = qubit + 2 < activeQubits.length ? qubit + 2 : (qubit - 2 >= 0 ? qubit - 2 : qubit);
						updated.controls = [qubit, q2];
						updated.target = q3;
					}
					return updated;
				}
				return op;
			});
		} else {
			const newOp: CircuitOp = {
				id: Math.random().toString(),
				gate: gateType,
				time: moment
			};

			if (['H', 'X', 'Y', 'Z', 'S', 'T', 'M', 'Reset', 'PhasedXZ', 'XPow'].includes(gateType)) {
				newOp.target = qubit;
			} else if (['RX', 'RY', 'RZ'].includes(gateType)) {
				newOp.target = qubit;
				newOp.param = 'pi/2';
			} else if (gateType === 'CX' || gateType === 'CZ' || gateType === 'FSim') {
				newOp.control = qubit;
				newOp.target = qubit + 1 < activeQubits.length ? qubit + 1 : qubit - 1;
			} else if (gateType === 'SWAP') {
				const q2 = qubit + 1 < activeQubits.length ? qubit + 1 : qubit - 1;
				newOp.targets = [qubit, q2];
			} else if (gateType === 'CCX') {
				const q2 = qubit + 1 < activeQubits.length ? qubit + 1 : qubit - 1;
				const q3 = qubit + 2 < activeQubits.length ? qubit + 2 : (qubit - 2 >= 0 ? qubit - 2 : qubit);
				newOp.controls = [qubit, q2];
				newOp.target = q3;
			}

			circuitState.push(newOp);
		}

		draggedGateType = null;
		draggedOpId = null;
		dragOverCell = null;
	}

	function getAffectedQubits(gateType: string, baseQubit: number): number[] {
		if (['CX', 'CZ', 'SWAP', 'FSim'].includes(gateType)) {
			const q2 = baseQubit + 1 < activeQubits.length ? baseQubit + 1 : baseQubit - 1;
			return [baseQubit, q2];
		}
		if (gateType === 'CCX') {
			const q2 = baseQubit + 1 < activeQubits.length ? baseQubit + 1 : baseQubit - 1;
			const q3 = baseQubit + 2 < activeQubits.length ? baseQubit + 2 : (baseQubit - 2 >= 0 ? baseQubit - 2 : baseQubit);
			return [baseQubit, q2, q3];
		}
		return [baseQubit];
	}

	function handleGateClick(event: MouseEvent, op: CircuitOp) {
		event.stopPropagation();
		editingOp = op;
		contextMenuPos = { x: event.clientX, y: event.clientY };
	}

	function deleteOp(id: string) {
		circuitState = circuitState.filter(op => op.id !== id);
		editingOp = null;
		contextMenuPos = null;
	}

	function closeContextMenu() {
		editingOp = null;
		contextMenuPos = null;
	}

	// --- Simulation Methods ---
	async function autoRunSimulation() {
		const circuitJson = compileStateToCirqJson();
		const parsed = JSON.parse(circuitJson);
		if (parsed.moments.length === 0) return;

		const payload: Record<string, any> = {
			circuit: circuitJson,
			target: workspaceMode === 'normal' ? 'generic' : 'generic',
			simulation_type: (workspaceMode === 'research' && (thermalNoise || depolarizingNoise)) ? 'noisy' : 'perfect',
			repetitions: Number(repetitions),
			return_state_vector: returnStateVector
		};

		if (workspaceMode === 'research' && payload.simulation_type === 'noisy') {
			payload.noise_config = {
				type: 'depolarizing',
				p: Number(noiseProbability),
				readout_p: Number(noiseProbability * 0.5)
			};
		}

		try {
			const res = await fetch('http://localhost:8080/api/jobs', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});
			if (res.ok) {
				const data = await res.json();
				pollSilentJob(data.job_id);
			}
		} catch (e) {
			// Silent error catch
		}
	}

	async function pollSilentJob(jobId: string) {
		let attempts = 0;
		const interval = setInterval(async () => {
			attempts++;
			if (attempts > 12) clearInterval(interval);
			try {
				const res = await fetch(`http://localhost:8080/api/jobs/${jobId}`);
				if (res.ok) {
					const data = await res.json();
					if (data.status === 'COMPLETED') {
						simulationResults = data.result;
						clearInterval(interval);
					} else if (data.status === 'FAILED') {
						clearInterval(interval);
					}
				}
			} catch (e) {
				clearInterval(interval);
			}
		}, 500);
	}

	async function runPipelineManual() {
		isRunning = true;
		jobStatus = 'SUBMITTING';
		jobError = null;

		const circuitJson = compileStateToCirqJson();
		const parsed = JSON.parse(circuitJson);
		if (parsed.moments.length === 0) {
			jobStatus = null;
			jobError = 'Cannot execute an empty circuit.';
			isRunning = false;
			return;
		}

		const targetVal = workspaceMode === 'normal' ? 'generic' : (researchBackend === 'ideal_qsim' ? 'generic' : 'sycamore');
		const simTypeVal = (workspaceMode === 'research' && (thermalNoise || depolarizingNoise)) ? 'noisy' : 'perfect';

		const payload: Record<string, any> = {
			circuit: circuitJson,
			target: targetVal,
			simulation_type: simTypeVal,
			repetitions: Number(repetitions),
			return_state_vector: returnStateVector
		};

		if (simTypeVal === 'noisy') {
			payload.noise_config = {
				type: 'depolarizing',
				p: Number(noiseProbability),
				readout_p: Number(noiseProbability * 0.5)
			};
		}

		try {
			const res = await fetch('http://localhost:8080/api/jobs', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(payload)
			});

			if (!res.ok) {
				const body = await res.json();
				throw new Error(body.error || 'Failed to submit pipeline job');
			}

			const data = await res.json();
			activeJobId = data.job_id;
			jobStatus = 'QUEUED';

			pollJobStatus(data.job_id);
		} catch (err: any) {
			jobStatus = 'FAILED';
			jobError = err.message || 'Pipeline request failed.';
			isRunning = false;
		}
	}

	async function pollJobStatus(jobId: string) {
		const interval = setInterval(async () => {
			try {
				const res = await fetch(`http://localhost:8080/api/jobs/${jobId}`);
				if (!res.ok) throw new Error('Job details unreachable');
				const data = await res.json();
				jobStatus = data.status;

				if (data.status === 'COMPLETED') {
					clearInterval(interval);
					simulationResults = data.result;
					isRunning = false;
				} else if (data.status === 'FAILED') {
					clearInterval(interval);
					jobError = data.error || 'Execution failed on backend.';
					isRunning = false;
				}
			} catch (err: any) {
				clearInterval(interval);
				jobStatus = 'FAILED';
				jobError = err.message;
				isRunning = false;
			}
		}, 800);
	}

	function highlightCodeSyntax(code: string): string {
		let html = code
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;');

		const keywords = [
			'import', 'from', 'as', 'def', 'print', 'for', 'in', 'if', 'else', 'while', 'class', 'return'
		];
		keywords.forEach(kw => {
			const reg = new RegExp(`\\b${kw}\\b`, 'g');
			html = html.replace(reg, `<span class="code-kw">${kw}</span>`);
		});

		html = html.replace(/(\w+)(?=\()/g, '<span class="code-fn">$1</span>');
		html = html.replace(/(["'])(.*?)\1/g, '<span class="code-str">"$2"</span>');
		html = html.replace(/(#.*)/g, '<span class="code-comment">$1</span>');
		html = html.replace(/\b(\d+)\b/g, '<span class="code-num">$1</span>');

		return html;
	}

	// --- Three.js Q-sphere ---
	let scene: THREE.Scene | null = null;
	let camera: THREE.PerspectiveCamera | null = null;
	let renderer: THREE.WebGLRenderer | null = null;
	let sphereGroup: THREE.Group | null = null;
	let nodeMeshes: THREE.Mesh[] = [];
	let connectionLines: THREE.Line[] = [];
	let sphereLabels: any[] = [];
	let labelOverlayElements = $state<{ text: string; x: number; y: number; color: string; visible: boolean }[]>([]);

	let animId: number | null = null;
	let qsphereResizeObserver: ResizeObserver | null = null;
	let qsphereContainer = $state<HTMLDivElement | null>(null);
	let onMouseUpListener: (() => void) | null = null;

	function initThreeQSphere(container: HTMLDivElement) {
		if (typeof window === 'undefined' || !container) return;

		const rect = container.getBoundingClientRect();
		const w = rect.width || 280;
		const h = rect.height || 280;

		scene = new THREE.Scene();
		camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 50);
		camera.position.set(0, 0, 5.5);

		renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
		renderer.setSize(w, h);
		renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
		container.innerHTML = '';
		container.appendChild(renderer.domElement);

		const ambient = new THREE.AmbientLight(0xffffff, 0.6);
		scene.add(ambient);

		const p1 = new THREE.PointLight(0xa78bfa, 1.2, 50);
		p1.position.set(5, 5, 5);
		scene.add(p1);

		const p2 = new THREE.PointLight(0x06b6d4, 0.9, 50);
		p2.position.set(-5, -5, 5);
		scene.add(p2);

		sphereGroup = new THREE.Group();
		// Tilts
		sphereGroup.rotation.x = 0.3;
		sphereGroup.rotation.y = 0.55;
		scene.add(sphereGroup);

		// Translucent sphere wireframe
		const sphereGeo = new THREE.SphereGeometry(2, 24, 24);
		const sphereMat = new THREE.MeshBasicMaterial({
			color: 0x475569,
			wireframe: true,
			transparent: true,
			opacity: 0.1
		});
		const sphereWireframe = new THREE.Mesh(sphereGeo, sphereMat);
		sphereGroup.add(sphereWireframe);

		// Equator
		const equatorGeo = new THREE.RingGeometry(1.99, 2.01, 64);
		const equatorMat = new THREE.MeshBasicMaterial({
			color: 0x475569,
			side: THREE.DoubleSide,
			transparent: true,
			opacity: 0.2
		});
		const equator = new THREE.Mesh(equatorGeo, equatorMat);
		equator.rotation.x = Math.PI / 2;
		sphereGroup.add(equator);

		// Guide lines
		const R = 2;
		const addAxisGuide = (pStart: THREE.Vector3, pEnd: THREE.Vector3, color: number) => {
			const pts = [pStart, pEnd];
			const geo = new THREE.BufferGeometry().setFromPoints(pts);
			const mat = new THREE.LineDashedMaterial({
				color,
				dashSize: 0.15,
				gapSize: 0.1,
				transparent: true,
				opacity: 0.25
			});
			const line = new THREE.Line(geo, mat);
			line.computeLineDistances();
			sphereGroup!.add(line);
		};

		addAxisGuide(new THREE.Vector3(0, -R, 0), new THREE.Vector3(0, R, 0), 0xa78bfa); // Y poles
		addAxisGuide(new THREE.Vector3(0, 0, -R), new THREE.Vector3(0, 0, R), 0x06b6d4); // Z poles
		addAxisGuide(new THREE.Vector3(-R, 0, 0), new THREE.Vector3(R, 0, 0), 0x475569); // X poles

		// Interactivity
		let isDragging = false;
		let prevPos = { x: 0, y: 0 };
		const dom = renderer.domElement;

		dom.addEventListener('mousedown', (e: MouseEvent) => {
			isDragging = true;
			prevPos = { x: e.clientX, y: e.clientY };
		});
		dom.addEventListener('mousemove', (e: MouseEvent) => {
			if (!isDragging || !sphereGroup) return;
			const dx = e.clientX - prevPos.x;
			const dy = e.clientY - prevPos.y;
			sphereGroup.rotation.y += dx * 0.005;
			sphereGroup.rotation.x += dy * 0.005;
			prevPos = { x: e.clientX, y: e.clientY };
		});
		onMouseUpListener = () => { isDragging = false; };
		window.addEventListener('mouseup', onMouseUpListener);

		// Animate
		function animate() {
			if (!renderer || !scene || !camera) return;
			animId = requestAnimationFrame(animate);
			renderer.render(scene, camera);
			updateHTMLOverlayLabels(container);
		}
		animate();

		qsphereResizeObserver = new ResizeObserver(() => {
			if (!container || !renderer || !camera) return;
			const rect = container.getBoundingClientRect();
			const w = rect.width || 280;
			const h = rect.height || 280;
			renderer.setSize(w, h);
			camera.aspect = w / h;
			camera.updateProjectionMatrix();
		});
		qsphereResizeObserver.observe(container);

		if (simulationResults && simulationResults.state_vector) {
			updateQSphere(simulationResults.state_vector);
		}
	}

	function cleanupThreeQSphere() {
		if (animId !== null) {
			cancelAnimationFrame(animId);
			animId = null;
		}
		if (qsphereResizeObserver) {
			qsphereResizeObserver.disconnect();
			qsphereResizeObserver = null;
		}
		if (onMouseUpListener) {
			window.removeEventListener('mouseup', onMouseUpListener);
			onMouseUpListener = null;
		}
		if (renderer) {
			renderer.dispose();
			renderer = null;
		}
		scene = null;
		camera = null;
		sphereGroup = null;
		nodeMeshes = [];
		connectionLines = [];
		sphereLabels = [];
		labelOverlayElements = [];
	}

	function updateQSphere(sv: number[]) {
		if (!scene || !sphereGroup) return;

		nodeMeshes.forEach(m => sphereGroup!.remove(m));
		nodeMeshes = [];
		connectionLines.forEach(l => sphereGroup!.remove(l));
		connectionLines = [];
		sphereLabels = [];

		const N = activeQubits.length;
		const totalStates = 1 << N;
		const R = 2;

		let stateVec = sv;
		if (!stateVec || stateVec.length !== totalStates * 2) {
			stateVec = new Array(totalStates * 2).fill(0);
			stateVec[0] = 1.0; 
		}

		// Static reference coordinate labels
		sphereLabels.push({ text: "|0⟩", position: new THREE.Vector3(0, R + 0.15, 0), amp: 1.0, color: '#a78bfa', isStatic: true });
		sphereLabels.push({ text: "|1⟩", position: new THREE.Vector3(0, -(R + 0.15), 0), amp: 1.0, color: '#f472b6', isStatic: true });
		sphereLabels.push({ text: "|+⟩", position: new THREE.Vector3(0, 0, R + 0.15), amp: 1.0, color: '#06b6d4', isStatic: true });
		sphereLabels.push({ text: "|-⟩", position: new THREE.Vector3(0, 0, -(R + 0.15)), amp: 1.0, color: '#fb923c', isStatic: true });
		sphereLabels.push({ text: "|i⟩", position: new THREE.Vector3(R + 0.15, 0, 0), amp: 1.0, color: '#c084fc', isStatic: true });
		sphereLabels.push({ text: "|-i⟩", position: new THREE.Vector3(-(R + 0.15), 0, 0), amp: 1.0, color: '#e9d5ff', isStatic: true });

		for (let k = 0; k <= N; k++) {
			const states = getStatesWithHammingWeight(N, k);
			const Mk = states.length;
			const theta = (k * Math.PI) / N;

			states.forEach((stateIndex: number, j: number) => {
				const phi = Mk > 1 ? (j * 2 * Math.PI) / Mk : 0;

				const x = R * Math.sin(theta) * Math.cos(phi);
				const y = R * Math.cos(theta); // Vertical Y poles
				const z = R * Math.sin(theta) * Math.sin(phi);

				const real = stateVec[stateIndex * 2];
				const imag = stateVec[stateIndex * 2 + 1];
				const amp = Math.sqrt(real * real + imag * imag);
				const phase = Math.atan2(imag, real);
				const posPhase = phase < 0 ? phase + 2 * Math.PI : phase;

				const hue = (posPhase * 180) / Math.PI;
				const color = new THREE.Color(`hsl(${hue}, 95%, 55%)`);
				const radius = 0.05 + amp * 0.22;

				const geo = new THREE.SphereGeometry(radius, 16, 16);
				let mat;
				if (amp > 0.01) {
					mat = new THREE.MeshPhongMaterial({
						color,
						emissive: color,
						emissiveIntensity: 0.6,
						shininess: 100
					});
				} else {
					mat = new THREE.MeshBasicMaterial({
						color: 0x334155,
						transparent: true,
						opacity: 0.2
					});
				}

				const mesh = new THREE.Mesh(geo, mat);
				mesh.position.set(x, y, z);
				sphereGroup!.add(mesh);
				nodeMeshes.push(mesh);

				const binText = `|${stateIndex.toString(2).padStart(N, '0')}⟩`;
				sphereLabels.push({
					text: binText,
					position: new THREE.Vector3(x, y, z),
					amp,
					color: '#f8fafc',
					isStatic: false
				});

				if (amp > 0.01) {
					const pts = [new THREE.Vector3(0,0,0), new THREE.Vector3(x, y, z)];
					const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
					const lineMat = new THREE.LineBasicMaterial({
						color,
						transparent: true,
						opacity: 0.7
					});
					const line = new THREE.Line(lineGeo, lineMat);
					sphereGroup!.add(line);
					connectionLines.push(line);
				}
			});
		}
	}

	function updateHTMLOverlayLabels(container: HTMLDivElement) {
		if (!camera || !renderer || !container || sphereLabels.length === 0 || !sphereGroup) return;

		const rect = container.getBoundingClientRect();
		const w = rect.width;
		const h = rect.height;

		const tempV = new THREE.Vector3();
		const list = [];

		for (const label of sphereLabels) {
			if (label.isStatic || label.amp > 0.04) {
				tempV.copy(label.position);
				tempV.applyQuaternion(sphereGroup.quaternion);
				tempV.project(camera);

				const visible = tempV.z <= 1.0;
				const x = (tempV.x * 0.5 + 0.5) * w;
				const y = (-tempV.y * 0.5 + 0.5) * h;

				list.push({
					text: label.isStatic ? label.text : label.text + ` (${(label.amp * label.amp * 100).toFixed(0)}%)`,
					x,
					y,
					color: label.color,
					visible
				});
			}
		}
		labelOverlayElements = list;
	}
</script>

<div class="app-wrapper theme-dark">
	<!-- Top Navigation Header -->
	<header class="navbar-header">
		<div class="navbar-left">
			<div class="navbar-logo">
				<span class="icon-logo">⚛</span>
				<span class="app-title">Advanced Quantum Composer <span>Studio</span></span>
			</div>
		</div>

		<div class="navbar-right">
			<!-- Normal vs Research Mode Toggle -->
			<div class="mode-toggle-group">
				<span class="mode-lbl">Workspace Mode:</span>
				<button class="btn-mode-toggle" class:active={workspaceMode === 'normal'} onclick={() => workspaceMode = 'normal'}>Normal</button>
				<button class="btn-mode-toggle" class:active={workspaceMode === 'research'} onclick={() => workspaceMode = 'research'}>Research</button>
			</div>

			<div class="health-status">
				<span class="health-dot {gatewayHealth}"></span>
				<span class="health-text">Gateway: {gatewayHealth}</span>
			</div>
		</div>
	</header>

	<div class="studio-layout">
		<!-- Left Panel: Gate Palette & Advanced settings -->
		<aside class="left-settings-sidebar">
			<div class="panel-section">
				<div class="panel-section-header">
					<h3 class="panel-title-text">Gate Palette</h3>
					{#if workspaceMode === 'research'}
						<div class="gate-set-toggle">
							<button class="btn-gate-set" class:active={gateSet === 'standard'} onclick={() => gateSet = 'standard'}>Standard</button>
							<button class="btn-gate-set" class:active={gateSet === 'native'} onclick={() => gateSet = 'native'}>Cirq Native</button>
						</div>
					{/if}
				</div>

				<div class="gate-palette-grid">
					{#each gateGroups as group, idx}
						<div class="palette-subgroup">
							<span class="group-label">{group.name}</span>
							<div class="group-gates-vertical">
								{#each group.gates as gate}
									<div 
										class="gate-tile {group.colorClass}"
										draggable="true"
										ondragstart={(e) => handlePaletteDragStart(e, gate.type)}
										title={gate.description}
										role="button"
										tabindex="0"
									>
										<span class="gate-tile-symbol">{gate.type === 'CX' ? '⊕' : gate.type}</span>
										<span class="gate-tile-name">{gate.name}</span>
									</div>
								{/each}
							</div>
						</div>
						{#if idx < gateGroups.length - 1}
							<div class="palette-divider"></div>
						{/if}
					{/each}
				</div>
			</div>

			<!-- Simulator Settings Configurations -->
			<div class="panel-section settings-section">
				<h3 class="panel-title-text">Simulator Settings</h3>
				<div class="settings-body">
					{#if workspaceMode === 'normal'}
						<!-- Simplified settings -->
						<div class="form-group">
							<label for="normal-backend">Simulation Backend</label>
							<select id="normal-backend" class="form-select" bind:value={normalBackend}>
								<option value="standard_sim">Standard Simulator</option>
							</select>
						</div>
					{:else}
						<!-- Advanced Research settings -->
						<div class="form-group">
							<label for="research-backend">Backend Target</label>
							<select id="research-backend" class="form-select" bind:value={researchBackend}>
								<option value="ideal_qsim">Ideal Simulator (QSim)</option>
								<option value="hardware_sycamore">Hardware Sycamore Emulator</option>
								<option value="tensor_network">Tensor-Network Simulator</option>
							</select>
						</div>

						<!-- Advanced Noise Model Configuration -->
						<div class="noise-configurator-card">
							<span class="config-sub-label">Noise Model Configurator</span>
							<div class="noise-toggle-row">
								<label class="checkbox-label">
									<input type="checkbox" bind:checked={depolarizingNoise}>
									<span class="custom-checkbox"></span>
									<span>Depolarizing Channel</span>
								</label>
							</div>
							<div class="noise-toggle-row">
								<label class="checkbox-label">
									<input type="checkbox" bind:checked={thermalNoise}>
									<span class="custom-checkbox"></span>
									<span>Thermal Relaxation</span>
								</label>
							</div>

							{#if depolarizingNoise || thermalNoise}
								<div class="form-group mt-2">
									<div class="slider-header">
										<label for="noise-probability-rate">Error Rate (p)</label>
										<span class="slider-val">{(noiseProbability * 100).toFixed(1)}%</span>
									</div>
									<input id="noise-probability-rate" type="range" min="0.001" max="0.1" step="0.001" class="form-range" bind:value={noiseProbability}>
								</div>
							{/if}
						</div>

						<div class="form-group checkbox-group">
							<label class="checkbox-label">
								<input type="checkbox" bind:checked={returnStateVector}>
								<span class="custom-checkbox"></span>
								<span>Return State Vector (Max 12 qubits)</span>
							</label>
						</div>
					{/if}

					<div class="form-group">
						<div class="slider-header">
							<label for="repetitions-rate">Shots / Repetitions</label>
							<span class="slider-val">{repetitions}</span>
						</div>
						<input id="repetitions-rate" type="range" min="100" max="5000" step="100" class="form-range" bind:value={repetitions}>
					</div>

					<div class="action-buttons mt-3">
						<button class="btn-run" onclick={runPipelineManual} disabled={isRunning}>
							{#if isRunning}
								<span class="spinner"></span> Executing...
							{:else}
								Run Circuit
							{/if}
						</button>
						<button class="btn-clear" onclick={clearCircuit} disabled={isRunning}>
							Clear Board
						</button>
					</div>
				</div>
			</div>
		</aside>

		<!-- Center Area: Circuit Canvas (Top) & Result Displays (Bottom) -->
		<main class="center-content">
			<!-- Canvas Section -->
			<section class="circuit-canvas-card">
				<div class="canvas-card-header">
					<h2 class="card-title-text">Circuit Builder</h2>
					
					<div class="header-controls">
						<div class="moments-configurator">
							<span class="view-badge">Moments: {maxMoments} (Auto-expanding)</span>
						</div>

						{#if workspaceMode === 'research'}
							<div class="topology-selector">
								<span class="view-label">Topology:</span>
								<button class="btn-topo-select" class:active={topology === 'line'} onclick={() => topology = 'line'}>Line Qubit</button>
								<button class="btn-topo-select" class:active={topology === 'grid'} onclick={() => topology = 'grid'}>Grid Qubit (2x3)</button>
							</div>
						{/if}
					</div>
				</div>

				<div class="circuit-editor-canvas">
					<div class="circuit-grid-container">
						<!-- Moments indicator -->
						<div class="moments-timeline">
							<div class="timeline-empty-corner"></div>
							{#each Array(maxMoments) as _, m}
								<div class="moment-label">Moment {m + 1}</div>
							{/each}
						</div>

						<div class="circuit-wires-grid">
							{#each activeQubits as qubit, qIndex}
								<div class="qubit-row">
									<div class="qubit-label-cell">
										<div class="qubit-badge">{qubit.name}</div>
									</div>

									<div class="wire-line"></div>

									{#each Array(maxMoments) as _, mIndex}
									{@const cellOp = getCellGate(mIndex, qubit.index)}
									{@const isViolated = cellOp ? checkCouplingViolation(cellOp) : false}
									
									<!-- svelte-ignore a11y_click_events_have_key_events -->
									<!-- svelte-ignore a11y_no_static_element_interactions -->
									<div 
										class="grid-cell 
											{dragOverCell?.moment === mIndex && dragOverCell?.qubit === qubit.index ? 'drag-over' : ''}
											{isViolated ? 'coupling-violation' : ''}
										"
										ondragover={handleDragOver}
										ondragenter={() => dragOverCell = { moment: mIndex, qubit: qubit.index }}
										ondragleave={() => {
											if (dragOverCell?.moment === mIndex && dragOverCell?.qubit === qubit.index) dragOverCell = null;
										}}
										ondrop={(e) => handleCanvasDrop(e, mIndex, qubit.index)}
										onclick={(e) => cellOp && handleGateClick(e, cellOp)}
										title={isViolated ? 'Coupling Map Constraint Violation: Qubits must be adjacent' : 'Click gate to edit'}
									>
										{#if cellOp}
											{#if ['H', 'X', 'Y', 'Z', 'S', 'T', 'M', 'Reset', 'PhasedXZ', 'XPow'].includes(cellOp.gate)}
												{@const groupColor = gateGroups.find(g => g.gates.some(t => t.type === cellOp.gate))?.colorClass}
												<div 
													class="gate-badge bg-gradient-to-br {groupColor}"
													draggable="true"
													ondragstart={(e) => handleCanvasDragStart(e, cellOp.id)}
												>
													{cellOp.gate === 'PhasedXZ' ? 'PXZ' : (cellOp.gate === 'Reset' ? 'R' : cellOp.gate)}
												</div>
											{:else if ['RX', 'RY', 'RZ'].includes(cellOp.gate)}
												<div 
													class="gate-badge bg-gradient-to-br parametric-gate"
													draggable="true"
													ondragstart={(e) => handleCanvasDragStart(e, cellOp.id)}
												>
													<span class="symbol-txt">{cellOp.gate}</span>
													{#if cellOp.param}
														<span class="param-txt">{cellOp.param}</span>
													{/if}
												</div>
											{:else if cellOp.gate === 'CX' || cellOp.gate === 'CZ' || cellOp.gate === 'FSim'}
												{#if cellOp.control === qubit.index}
													<div class="cnot-control-dot"></div>
												{:else if cellOp.target === qubit.index}
													<div class="cnot-target-cross">{cellOp.gate === 'CZ' ? '●' : (cellOp.gate === 'FSim' ? 'F' : '⊕')}</div>
												{/if}

												{#if cellOp.control === qubit.index && cellOp.target !== undefined}
													{@const dist = Math.abs(activeQubits.findIndex(q => q.index === cellOp.target) - qIndex)}
													{@const direction = cellOp.target > qubit.index ? 1 : -1}
													<div 
														class="cnot-connection-line {isViolated ? 'violation' : ''}"
														style="
															height: {dist * 60}px; 
															transform: translateY({direction === 1 ? 16 : -(dist * 60) + 16}px);
														"
													></div>
												{/if}
											{:else if cellOp.gate === 'SWAP'}
												{#if cellOp.targets?.includes(qubit.index)}
													<div class="swap-cross-marker">×</div>
												{/if}

												{@const targetVal1 = cellOp.targets?.[1]}
												{#if cellOp.targets && cellOp.targets[0] === qubit.index && targetVal1 !== undefined}
													{@const dist = Math.abs(activeQubits.findIndex(q => q.index === targetVal1) - qIndex)}
													{@const direction = targetVal1 > qubit.index ? 1 : -1}
													<div 
														class="cnot-connection-line swap-line {isViolated ? 'violation' : ''}"
														style="
															height: {dist * 60}px; 
															transform: translateY({direction === 1 ? 16 : -(dist * 60) + 16}px);
														"
													></div>
												{/if}
											{:else if cellOp.gate === 'CCX'}
												{#if cellOp.controls?.includes(qubit.index)}
													<div class="cnot-control-dot"></div>
												{:else if cellOp.target === qubit.index}
													<div class="cnot-target-cross">⊕</div>
												{/if}

												{#if cellOp.controls && cellOp.controls[0] !== undefined && cellOp.controls[1] !== undefined && cellOp.target !== undefined}
													{@const c0 = cellOp.controls[0]}
													{@const c1 = cellOp.controls[1]}
													{@const mapIndices = [c0, c1, cellOp.target].map(idx => activeQubits.findIndex(q => q.index === idx))}
													{@const minMap = Math.min(...mapIndices)}
													{@const maxMap = Math.max(...mapIndices)}
													{@const dist = maxMap - minMap}
													{#if qIndex === activeQubits.findIndex(q => q.index === c0)}
														<div 
															class="cnot-connection-line ccx-line {isViolated ? 'violation' : ''}"
															style="
																height: {dist * 60}px; 
																transform: translateY(16px);
															"
														></div>
													{/if}
												{/if}
											{/if}
										{/if}
									</div>
								{/each}
							</div>
						{/each}
					</div>
				</div>
			</div>

				<div class="canvas-qubit-actions">
					{#if workspaceMode === 'normal' || topology === 'line'}
						<button class="btn-canvas-action" onclick={addQubit}>+ Qubit</button>
						<button class="btn-canvas-action" onclick={removeQubit} disabled={lineQubits.length <= 1}>- Qubit</button>
					{:else}
						<div class="grid-dimensions-controls">
							<span class="dimension-label">Rows: {gridRows}</span>
							<button class="btn-canvas-action" onclick={() => gridRows = Math.min(6, gridRows + 1)} disabled={gridRows >= 6}>+</button>
							<button class="btn-canvas-action" onclick={removeGridRow} disabled={gridRows <= 1}>-</button>
							
							<span class="dimension-label ml-4">Cols: {gridCols}</span>
							<button class="btn-canvas-action" onclick={() => gridCols = Math.min(8, gridCols + 1)} disabled={gridCols >= 8}>+</button>
							<button class="btn-canvas-action" onclick={removeGridCol} disabled={gridCols <= 1}>-</button>
						</div>
					{/if}
				</div>
			</section>

			<!-- Resizable Bottom Visualizations Dock -->
			<footer class="visualizations-dock-card" class:collapsed={bottomCollapsed}>
				<header class="dock-header">
					<button class="btn-dock-toggle" onclick={() => bottomCollapsed = !bottomCollapsed}>
						<span class="dock-arrow-icon">{bottomCollapsed ? '▲' : '▼'}</span>
					</button>
					<h3 class="dock-title-text">Execution Visualizations</h3>

					{#if !bottomCollapsed}
						<div class="dock-tab-menu">
							<button class="dock-tab-btn" class:active={activeTab === 'histogram'} onclick={() => activeTab = 'histogram'}>Probabilities Histogram</button>
							
							{#if workspaceMode === 'research'}
								{#if topology === 'line'}
									<button class="dock-tab-btn" class:active={activeTab === 'qsphere'} onclick={() => activeTab = 'qsphere'}>3D State Q-sphere</button>
								{:else}
									<button class="dock-tab-btn" class:active={activeTab === 'coupling_map'} onclick={() => activeTab = 'coupling_map'}>2D Coupling Heatmap</button>
								{/if}
							{/if}
						</div>
					{/if}
				</header>

				{#if !bottomCollapsed}
					<div class="dock-body-content">
						{#if activeTab === 'histogram'}
							<!-- Probabilities vertical histogram -->
							<div class="visuals-tab-pane">
								{#if simulationResults}
									<div class="vertical-histogram-chart">
										{#each Object.entries(simulationResults.results) as [state, count]}
											{@const percentage = ((count / totalHistogramCount) * 100)}
											<div class="bar-chart-column">
												<span class="bar-percent">{percentage.toFixed(1)}%</span>
												<div class="bar-chart-track">
													<div class="bar-chart-fill" style="height: {percentage}%"></div>
												</div>
												<span class="bar-state-label">{formatStateLabelBinary(state, activeQubits.length)}</span>
											</div>
										{/each}
									</div>
								{:else}
									<div class="empty-vis-state">No simulation results. Run simulation or place gates to preview.</div>
								{/if}
							</div>
						{:else if activeTab === 'qsphere'}
							<!-- Line mode Q-sphere -->
							<div class="visuals-tab-pane qsphere-pane">
								<div class="qsphere-wrapper-card">
									<div bind:this={qsphereContainer} id="qsphere-webgl-container" class="canvas-webgl-renderer"></div>
									<div class="qsphere-overlay-labels">
										{#each labelOverlayElements as lbl}
											{#if lbl.visible}
												<div class="q-sphere-label" style="left: {lbl.x}px; top: {lbl.y}px; color: {lbl.color}">
													{lbl.text}
												</div>
											{/if}
										{/each}
									</div>
								</div>
								<div class="state-vector-amplitudes-list">
									<span class="pane-subtitle-txt">State Vector Amplitudes</span>
									{#if simulationResults && simulationResults.state_vector}
										<div class="sv-viewer-scroll">
											{#each stateVectorDetails as detail}
												<div class="sv-detail-row">
													<span class="sv-state-label">|{detail.state}⟩</span>
													<span class="sv-complex-num">{detail.real.toFixed(3)} {detail.imag >= 0 ? '+' : '-'} {Math.abs(detail.imag).toFixed(3)}i</span>
													<div class="sv-bar-track">
														<div class="sv-bar-fill" style="width: {detail.amp * 100}%"></div>
													</div>
													<span class="sv-val-amp">{detail.amp.toFixed(3)} (∠{detail.phase.toFixed(0)}°)</span>
												</div>
											{/each}
										</div>
									{:else}
										<div class="empty-vis-state">State vector not returned.</div>
									{/if}
								</div>
							</div>
						{:else if activeTab === 'coupling_map'}
							<!-- 2D Coupling Map Grid Heatmap -->
							<div class="visuals-tab-pane coupling-map-pane">
								<div class="coupling-lattice-graph">
									<span class="pane-subtitle-txt">Coupling Map Topology ({gridRows}x{gridCols} Qubit Lattice)</span>
									<div class="lattice-workspace">
										<!-- Coupling wires mapping -->
										<svg class="lattice-svg" viewBox="0 0 {100 + (gridCols - 1) * 80} {100 + (gridRows - 1) * 80}">
											<!-- Connections background -->
											<!-- Horizontal lines -->
											{#each Array(gridRows) as _, r}
												{#each Array(gridCols - 1) as _, c}
													{@const q1 = r * 10 + c}
													{@const q2 = r * 10 + c + 1}
													<line 
														x1={50 + c * 80} 
														y1={50 + r * 80} 
														x2={50 + (c + 1) * 80} 
														y2={50 + r * 80} 
														class="coupling-line" 
														class:active={isCouplingActive(q1, q2)} 
													/>
												{/each}
											{/each}
											<!-- Vertical lines -->
											{#each Array(gridRows - 1) as _, r}
												{#each Array(gridCols) as _, c}
													{@const q1 = r * 10 + c}
													{@const q2 = (r + 1) * 10 + c}
													<line 
														x1={50 + c * 80} 
														y1={50 + r * 80} 
														x2={50 + c * 80} 
														y2={50 + (r + 1) * 80} 
														class="coupling-line" 
														class:active={isCouplingActive(q1, q2)} 
													/>
												{/each}
											{/each}

											<!-- Qubits nodes drawing -->
											{#each gridQubits as qNode}
												{@const cx = 50 + qNode.col * 80}
												{@const cy = 50 + qNode.row * 80}
												{@const prob1 = getQubitProbability1(qNode.index)}
												
												<!-- Color node dynamically based on prob1 -->
												<circle 
													cx={cx} 
													cy={cy} 
													r="22" 
													fill="rgba(139, 92, 246, {0.1 + prob1 * 0.8})" 
													stroke="#a78bfa" 
													stroke-width="2" 
													class="lattice-qubit-circle"
												/>
												<text 
													x={cx} 
													y={cy - 2} 
													fill="#ffffff" 
													font-size="10" 
													font-weight="bold" 
													text-anchor="middle"
												>
													q({qNode.row},{qNode.col})
												</text>
												<text 
													x={cx} 
													y={cy + 12} 
													fill="#a78bfa" 
													font-size="9" 
													text-anchor="middle"
												>
													P(1): {(prob1 * 100).toFixed(0)}%
												</text>
											{/each}
										</svg>
									</div>
								</div>
								<div class="coupling-instructions">
									The 2D Coupling Heatmap represents physical layout adjacent linkages. Circular nodes illuminate dynamically matching $|1\rangle$ probability results (intensity maps to higher projection probabilities).
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</footer>

			<!-- Job status monitor pipeline -->
			{#if jobStatus}
				<div class="dock-status-pipeline mt-2">
					<div class="status-indicator">
						<span class="status-pulse-dot {jobStatus}"></span>
						<span class="status-lbl">Pipeline Status: <strong>{jobStatus}</strong></span>
					</div>
					{#if activeJobId}
						<span class="job-id-lbl">ID: {activeJobId}</span>
					{/if}
					{#if jobError}
						<div class="error-strip">{jobError}</div>
					{/if}
				</div>
			{/if}
		</main>

		<!-- Right Panel: Collapsible Google Cirq Code drawer -->
		<aside class="right-code-sidebar" class:collapsed={rightCollapsed}>
			{#if rightCollapsed}
				<button class="btn-expand-sidebar" onclick={() => rightCollapsed = false}>
					<span class="vertical-title-txt">GOOGLE CIRQ CODE</span>
					<span class="expand-arrow">◀</span>
				</button>
			{:else}
				<div class="panel-section-header code-header">
					<button class="btn-collapse-sidebar" onclick={() => rightCollapsed = true}>▶</button>
					<span class="code-title-lbl">Google Cirq Script</span>
					
					{#if workspaceMode === 'research'}
						<button class="btn-compile-preview" class:active={compilationPreview} onclick={() => compilationPreview = !compilationPreview}>
							Compile Options
						</button>
					{/if}
				</div>

				<div class="code-editor-body">
					<div class="code-utilities-row">
						<button class="btn-copy-code" onclick={() => {
							navigator.clipboard.writeText(cirqCode);
							alert('Google Cirq code copied to clipboard!');
						}}>Copy Script</button>
					</div>
					<pre class="code-editor-area"><code>{@html highlightedCode}</code></pre>
				</div>
			{/if}
		</aside>
	</div>

	<!-- Collapsible context menu popup for placed gates -->
	{#if editingOp && contextMenuPos}
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="context-menu-backdrop" onclick={closeContextMenu}></div>
		<div class="gate-context-menu" style="left: {contextMenuPos.x}px; top: {contextMenuPos.y}px;">
			<h4 class="menu-title">Editing: {editingOp.gate}</h4>

			{#if ['RX', 'RY', 'RZ'].includes(editingOp.gate)}
				<div class="menu-field">
					<label for="param-input">Angle (rad):</label>
					<input 
						id="param-input"
						type="text" 
						bind:value={editingOp.param} 
						placeholder="pi/2" 
						class="menu-input"
					/>
				</div>
			{/if}

			{#if ['CX', 'CZ', 'FSim'].includes(editingOp.gate)}
				<div class="menu-field">
					<label for="control-input">Control index:</label>
					<input 
						id="control-input"
						type="number" 
						min="0" 
						max={activeQubits.length - 1} 
						bind:value={editingOp.control} 
						class="menu-input"
					/>
				</div>
				<div class="menu-field">
					<label for="target-input">Target index:</label>
					<input 
						id="target-input"
						type="number" 
						min="0" 
						max={activeQubits.length - 1} 
						bind:value={editingOp.target} 
						class="menu-input"
					/>
				</div>
			{/if}

			<div class="menu-actions">
				<button class="btn-menu-action delete" onclick={() => deleteOp(editingOp!.id)}>Delete</button>
				<button class="btn-menu-action" onclick={closeContextMenu}>Close</button>
			</div>
		</div>
	{/if}
</div>

<style>
	/* --- Advanced Premium Theme --- */
	:global(body) {
		margin: 0;
		padding: 0;
		background-color: #08090f;
		color: #f1f5f9;
		font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
		overflow: hidden;
		height: 100vh;
	}

	.app-wrapper {
		display: flex;
		flex-direction: column;
		height: 100vh;
		box-sizing: border-box;
		background: radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.04) 0%, transparent 40%),
		            radial-gradient(circle at 90% 80%, rgba(6, 182, 212, 0.04) 0%, transparent 40%);
	}

	/* --- Application Header --- */
	.navbar-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.65rem 1.25rem;
		height: 52px;
		background-color: rgba(13, 17, 36, 0.7);
		backdrop-filter: blur(16px);
		border-bottom: 1px solid rgba(139, 92, 246, 0.15);
		z-index: 10;
		box-sizing: border-box;
	}

	.navbar-logo {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		font-size: 1.05rem;
	}
	.icon-logo {
		font-size: 1.25rem;
		color: #a78bfa;
		text-shadow: 0 0 8px #a78bfa;
	}
	.app-title span {
		background: linear-gradient(135deg, #a78bfa 0%, #06b6d4 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		font-weight: 700;
	}

	.navbar-right {
		display: flex;
		align-items: center;
		gap: 1.5rem;
	}

	.mode-toggle-group {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.mode-lbl {
		font-size: 0.78rem;
		color: #94a3b8;
		font-weight: 500;
	}
	.btn-mode-toggle {
		background-color: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: #94a3b8;
		padding: 0.3rem 0.65rem;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-mode-toggle:hover {
		color: #f8fafc;
	}
	.btn-mode-toggle.active {
		background-color: rgba(167, 139, 250, 0.1);
		border-color: #a78bfa;
		color: #c084fc;
		box-shadow: 0 0 6px rgba(167, 139, 250, 0.25);
	}

	.health-status {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		background-color: rgba(255, 255, 255, 0.02);
		padding: 0.3rem 0.65rem;
		border-radius: 9999px;
		border: 1px solid rgba(255, 255, 255, 0.06);
		font-size: 0.75rem;
		color: #94a3b8;
	}
	.health-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
	.health-dot.checking { background-color: #f59e0b; }
	.health-dot.online { background-color: #10b981; box-shadow: 0 0 6px #10b981; }
	.health-dot.offline { background-color: #ef4444; }

	/* --- Workspace Layout --- */
	.studio-layout {
		display: flex;
		flex: 1;
		box-sizing: border-box;
		overflow: hidden;
		height: calc(100vh - 52px);
	}

	/* --- Left Sidebar (Palette & Settings) --- */
	.left-settings-sidebar {
		width: 320px;
		border-right: 1px solid rgba(139, 92, 246, 0.12);
		background-color: rgba(13, 17, 36, 0.45);
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		box-sizing: border-box;
		flex-shrink: 0;
	}

	.panel-section {
		padding: 1.25rem;
		border-bottom: 1px solid rgba(139, 92, 246, 0.12);
	}
	.panel-section.settings-section {
		border-bottom: none;
	}

	.panel-section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.85rem;
	}
	.panel-title-text {
		font-size: 0.9rem;
		font-weight: 600;
		color: #e2e8f0;
		margin: 0;
		letter-spacing: -0.01em;
	}

	.gate-set-toggle {
		display: flex;
		gap: 0.2rem;
	}
	.btn-gate-set {
		background: none;
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: #94a3b8;
		padding: 0.2rem 0.45rem;
		font-size: 0.68rem;
		font-weight: 600;
		border-radius: 3px;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-gate-set.active {
		background-color: rgba(167, 139, 250, 0.08);
		border-color: #a78bfa;
		color: #c084fc;
	}

	/* Gate Palette Grid */
	.gate-palette-grid {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.palette-subgroup {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}
	.palette-divider {
		height: 1px;
		background: linear-gradient(90deg, rgba(139, 92, 246, 0.15) 0%, rgba(139, 92, 246, 0.02) 50%, rgba(139, 92, 246, 0) 100%);
		margin: 0.5rem 0;
	}
	.group-label {
		font-size: 0.65rem;
		font-weight: 700;
		text-transform: uppercase;
		color: #64748b;
		letter-spacing: 0.04em;
	}
	.group-gates-vertical {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.45rem;
	}

	/* Gate Tiles */
	.gate-tile {
		aspect-ratio: 1;
		border-radius: 6px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		cursor: grab;
		box-shadow: 0 1px 3px rgba(0,0,0,0.3);
		transition: transform 0.15s, box-shadow 0.15s;
		box-sizing: border-box;
		border: 1px solid transparent;
	}
	.gate-tile:hover {
		transform: scale(1.05);
		box-shadow: 0 4px 8px rgba(0,0,0,0.4);
	}
	.gate-tile:active { cursor: grabbing; }
	.gate-tile-symbol {
		font-size: 0.82rem;
		font-weight: 800;
		line-height: 1.1;
	}
	.gate-tile-name {
		font-size: 0.5rem;
		font-weight: 600;
		text-transform: uppercase;
		margin-top: 0.05rem;
		text-align: center;
		width: 100%;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* Gate Theme colors */
	.classical-gate { background-color: #1e293b; border-color: #334155; color: #f1f5f9; }
	.pauli-gate { background-color: #0284c7; border-color: #0369a1; color: #ffffff; }
	.parametric-gate { background-color: #7e22ce; border-color: #6b21a8; color: #ffffff; }
	.multi-gate { background-color: #1d4ed8; border-color: #1e40af; color: #ffffff; }

	/* --- Settings Panel --- */
	.settings-body {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.form-group label {
		font-size: 0.75rem;
		font-weight: 500;
		color: #94a3b8;
	}
	.form-select {
		background-color: rgba(9, 11, 23, 0.7);
		border: 1px solid rgba(139, 92, 246, 0.25);
		color: inherit;
		border-radius: 6px;
		padding: 0.45rem 0.65rem;
		font-size: 0.8rem;
		outline: none;
	}
	.form-select:focus {
		border-color: #a78bfa;
	}

	/* Noise card */
	.noise-configurator-card {
		background-color: rgba(0,0,0,0.25);
		border: 1px solid rgba(139, 92, 246, 0.12);
		border-radius: 6px;
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
	}
	.config-sub-label {
		font-size: 0.72rem;
		font-weight: 600;
		text-transform: uppercase;
		color: #c084fc;
		letter-spacing: 0.02em;
	}
	.noise-toggle-row {
		display: flex;
		align-items: center;
	}

	.checkbox-group { margin-top: 0.2rem; }
	.checkbox-label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
		font-size: 0.75rem;
		color: #94a3b8;
		user-select: none;
	}
	.checkbox-label input { display: none; }
	.custom-checkbox {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		border: 1px solid rgba(167, 139, 250, 0.5);
		background-color: rgba(0,0,0,0.3);
		display: inline-block;
		position: relative;
		flex-shrink: 0;
	}
	.checkbox-label input:checked + .custom-checkbox {
		background-color: #a78bfa;
		border-color: #a78bfa;
	}
	.checkbox-label input:checked + .custom-checkbox::after {
		content: '';
		position: absolute;
		left: 4px;
		top: 1.5px;
		width: 3px;
		height: 6px;
		border: solid #08090f;
		border-width: 0 1.5px 1.5px 0;
		transform: rotate(45deg);
	}

	.slider-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.slider-val {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		color: #06b6d4;
	}
	.form-range {
		-webkit-appearance: none;
		width: 100%;
		height: 3px;
		background-color: rgba(255,255,255,0.08);
		outline: none;
		border-radius: 2px;
	}
	.form-range::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: #a78bfa;
		cursor: pointer;
		box-shadow: 0 0 6px rgba(167, 139, 250, 0.6);
	}

	.action-buttons {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}
	.btn-run {
		background: linear-gradient(135deg, #a78bfa 0%, #7c3aed 100%);
		border: none;
		border-radius: 6px;
		color: white;
		padding: 0.6rem;
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		box-shadow: 0 4px 10px rgba(167, 139, 250, 0.2);
	}
	.btn-run:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn-clear {
		background-color: rgba(255,255,255,0.02);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: 6px;
		color: #cbd5e1;
		padding: 0.5rem;
		font-size: 0.78rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-clear:hover {
		background-color: rgba(239, 68, 68, 0.08);
		border-color: rgba(239, 68, 68, 0.2);
		color: #f87171;
	}

	/* --- Center Workspace Canvas --- */
	.center-content {
		flex: 1;
		display: flex;
		flex-direction: column;
		padding: 1.25rem;
		gap: 1rem;
		overflow-y: auto;
		box-sizing: border-box;
	}

	.circuit-canvas-card {
		background-color: rgba(13, 17, 36, 0.45);
		border: 1px solid rgba(139, 92, 246, 0.12);
		border-radius: 12px;
		display: flex;
		flex-direction: column;
		padding: 1.25rem;
	}

	.canvas-card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}
	.card-title-text {
		font-size: 0.95rem;
		font-weight: 600;
		margin: 0;
		color: #e2e8f0;
	}

	.header-controls {
		display: flex;
		align-items: center;
		gap: 1.5rem;
	}
	.moments-configurator {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.view-badge {
		font-size: 0.72rem;
		color: #a78bfa;
		background-color: rgba(167, 139, 250, 0.08);
		border: 1px solid rgba(167, 139, 250, 0.2);
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
		font-weight: 600;
	}
	.moments-control-group {
		display: flex;
		align-items: center;
		background-color: rgba(9, 11, 23, 0.5);
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 6px;
		overflow: hidden;
		padding: 1px;
	}
	.btn-moment-control {
		background: none;
		border: none;
		color: #94a3b8;
		width: 26px;
		height: 26px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: bold;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-moment-control:hover:not(:disabled) {
		background-color: rgba(167, 139, 250, 0.1);
		color: #c084fc;
	}
	.btn-moment-control:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}
	.moments-input {
		background: none;
		border: none;
		color: #f8fafc;
		width: 38px;
		text-align: center;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		font-weight: 600;
		outline: none;
	}
	.moments-input::-webkit-outer-spin-button,
	.moments-input::-webkit-inner-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}

	.topology-selector {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.grid-dimensions-controls {
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}
	.dimension-label {
		font-size: 0.72rem;
		color: #94a3b8;
		font-weight: 600;
	}
	.ml-4 {
		margin-left: 1rem;
	}
	.view-label {
		font-size: 0.72rem;
		color: #94a3b8;
	}
	.btn-topo-select {
		background: none;
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: #94a3b8;
		padding: 0.25rem 0.55rem;
		font-size: 0.7rem;
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-topo-select.active {
		background-color: rgba(167, 139, 250, 0.1);
		border-color: #a78bfa;
		color: #c084fc;
	}

	/* Premium Custom Scrollbars */
	::-webkit-scrollbar {
		width: 6px;
		height: 6px;
	}
	::-webkit-scrollbar-track {
		background: rgba(255, 255, 255, 0.01);
		border-radius: 4px;
	}
	::-webkit-scrollbar-thumb {
		background: rgba(139, 92, 246, 0.2);
		border-radius: 4px;
		border: 1px solid rgba(255, 255, 255, 0.03);
	}
	::-webkit-scrollbar-thumb:hover {
		background: rgba(139, 92, 246, 0.4);
	}

	.circuit-editor-canvas {
		background-color: rgba(9, 11, 23, 0.35);
		border: 1px solid rgba(255, 255, 255, 0.03);
		border-radius: 8px;
		padding: 1rem;
		overflow-x: auto;
	}

	.circuit-grid-container {
		min-width: max-content;
		width: 100%;
		display: flex;
		flex-direction: column;
	}

	.moments-timeline {
		display: flex;
		align-items: center;
		margin-bottom: 0.4rem;
		flex-shrink: 0;
	}
	.timeline-empty-corner { width: 70px; flex-shrink: 0; }
	.moment-label {
		width: 52px;
		text-align: center;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.7rem;
		font-weight: 600;
		color: #4b5563;
		margin-left: 12px;
		flex-shrink: 0;
	}

	.circuit-wires-grid {
		display: flex;
		flex-direction: column;
		gap: 16px;
		padding: 6px 0;
	}

	.qubit-row {
		display: flex;
		align-items: center;
		position: relative;
		height: 44px;
		width: 100%;
	}

	.qubit-label-cell {
		width: 70px;
		flex-shrink: 0;
	}
	.qubit-badge {
		background-color: rgba(255, 255, 255, 0.03);
		border: 1px solid rgba(255, 255, 255, 0.06);
		padding: 0.2rem 0.45rem;
		border-radius: 4px;
		font-weight: 600;
		font-size: 0.75rem;
		text-align: center;
		width: 48px;
		font-family: 'JetBrains Mono', monospace;
	}

	.wire-line {
		position: absolute;
		left: 65px;
		right: 0;
		height: 2px;
		background: rgba(255, 255, 255, 0.06);
		z-index: 1;
	}

	.grid-cell {
		width: 52px;
		height: 42px;
		margin-left: 12px;
		background-color: transparent;
		border: 1px solid transparent;
		border-radius: 6px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		position: relative;
		z-index: 2;
		transition: border-color 0.2s, background-color 0.2s, transform 0.2s;
		flex-shrink: 0;
	}
	.grid-cell:hover {
		border-color: rgba(167, 139, 250, 0.35);
		border-style: dashed;
		background-color: rgba(167, 139, 250, 0.04);
	}
	.grid-cell.drag-over {
		border-color: #a78bfa;
		border-style: dashed;
		background-color: rgba(167, 139, 250, 0.12);
		transform: scale(1.03);
	}
	
	/* Coupling Constraint Warning Style */
	.grid-cell.coupling-violation {
		border-color: #ef4444 !important;
		background-color: rgba(239, 68, 68, 0.06) !important;
		animation: warning-glow 1.5s infinite ease-in-out;
	}
	@keyframes warning-glow {
		0%, 100% { box-shadow: 0 0 4px rgba(239, 68, 68, 0.1); }
		50% { box-shadow: 0 0 10px rgba(239, 68, 68, 0.3); }
	}

	.gate-badge {
		width: 32px;
		height: 32px;
		border-radius: 5px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 0.8rem;
		box-shadow: 0 2px 6px rgba(0,0,0,0.35);
		color: white;
		cursor: grab;
		position: relative;
		z-index: 5;
	}
	.gate-badge:active { cursor: grabbing; }
	.symbol-txt { line-height: 1.1; }
	.param-txt { font-size: 0.5rem; font-family: 'JetBrains Mono', monospace; opacity: 0.85; }

	/* Multi-qubit connection routing */
	.cnot-control-dot {
		width: 8px;
		height: 8px;
		background-color: #a78bfa;
		border-radius: 50%;
		z-index: 5;
	}
	.cnot-target-cross {
		width: 18px;
		height: 18px;
		border-radius: 50%;
		border: 1.5px solid #a78bfa;
		color: #a78bfa;
		background-color: #0d1124;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 0.8rem;
		z-index: 5;
	}
	.swap-cross-marker {
		font-size: 1.1rem;
		font-weight: 500;
		color: #1d4ed8;
		z-index: 5;
	}

	.cnot-connection-line {
		position: absolute;
		width: 2px;
		background: #a78bfa;
		left: 25px;
		z-index: 1;
		pointer-events: none;
	}
	.cnot-connection-line.swap-line { background: #1d4ed8; }
	.cnot-connection-line.violation { background: #ef4444 !important; }

	.canvas-qubit-actions {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.85rem;
	}
	.btn-canvas-action {
		background-color: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: #cbd5e1;
		padding: 0.35rem 0.75rem;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}
	.btn-canvas-action:hover {
		background-color: rgba(255, 255, 255, 0.05);
	}
	.btn-canvas-action:disabled { opacity: 0.5; cursor: not-allowed; }

	/* --- Visualizations dock Bottom Panel --- */
	.visualizations-dock-card {
		background-color: rgba(13, 17, 36, 0.45);
		border: 1px solid rgba(139, 92, 246, 0.12);
		border-radius: 12px;
		height: 380px;
		display: flex;
		flex-direction: column;
		box-sizing: border-box;
		overflow: hidden;
		transition: height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.visualizations-dock-card.collapsed {
		height: 38px;
	}

	.dock-header {
		display: flex;
		align-items: center;
		height: 38px;
		padding: 0.35rem 1rem;
		background-color: rgba(9, 11, 23, 0.4);
		border-bottom: 1px solid rgba(139, 92, 246, 0.1);
		box-sizing: border-box;
	}
	.btn-dock-toggle {
		background: none;
		border: none;
		color: #94a3b8;
		cursor: pointer;
		font-size: 0.75rem;
		padding: 0;
		margin-right: 0.5rem;
	}
	.dock-title-text {
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: #a78bfa;
		margin: 0;
	}

	.dock-tab-menu {
		display: flex;
		gap: 0.4rem;
		margin-left: 1.5rem;
	}
	.dock-tab-btn {
		background: none;
		border: none;
		color: #94a3b8;
		padding: 0.2rem 0.5rem;
		font-size: 0.72rem;
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		transition: all 0.2s;
	}
	.dock-tab-btn:hover { color: #f8fafc; }
	.dock-tab-btn.active {
		background-color: rgba(167, 139, 250, 0.08);
		color: #c084fc;
	}

	.dock-body-content {
		flex: 1;
		padding: 0.85rem;
		overflow: auto;
		display: flex;
		box-sizing: border-box;
	}

	.visuals-tab-pane {
		flex: 1;
		display: flex;
		height: 100%;
		box-sizing: border-box;
	}

	/* Histogram bar columns */
	.vertical-histogram-chart {
		display: flex;
		align-items: flex-end;
		justify-content: center;
		justify-content: safe center;
		gap: 12px;
		flex: 1;
		height: 100%;
		background-color: rgba(9, 11, 23, 0.3);
		border: 1px solid rgba(255, 255, 255, 0.02);
		border-radius: 6px;
		padding: 0.5rem;
		box-sizing: border-box;
		overflow-x: auto;
		width: 100%;
	}
	.bar-chart-column {
		display: flex;
		flex-direction: column;
		align-items: center;
		flex-shrink: 0;
		width: 48px;
		height: 100%;
		justify-content: flex-end;
	}
	.bar-percent {
		font-size: 0.65rem;
		font-weight: 600;
		font-family: 'JetBrains Mono', monospace;
		color: #e2e8f0;
		margin-bottom: 0.15rem;
	}
	.bar-chart-track {
		width: 22px;
		background-color: rgba(255, 255, 255, 0.02);
		border-radius: 3px;
		flex: 1;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
		overflow: hidden;
		border: 1px solid rgba(255, 255, 255, 0.04);
	}
	.bar-chart-fill {
		width: 100%;
		background: linear-gradient(180deg, #06b6d4 0%, #7c3aed 100%);
		border-radius: 2px;
		transition: height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
		box-shadow: 0 0 6px rgba(6, 182, 212, 0.3);
	}
	.bar-state-label {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.72rem;
		font-weight: 600;
		color: #a78bfa;
		margin-top: 0.35rem;
	}

	.empty-vis-state {
		font-size: 0.78rem;
		color: #64748b;
		text-align: center;
		width: 100%;
		padding-top: 2.5rem;
	}

	/* Q-sphere Visualizer Split */
	.qsphere-pane {
		gap: 1.5rem;
	}
	.qsphere-wrapper-card {
		flex: 1;
		background-color: rgba(9, 11, 23, 0.3);
		border: 1px solid rgba(255, 255, 255, 0.02);
		border-radius: 6px;
		position: relative;
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.canvas-webgl-renderer { width: 100%; height: 100%; }
	.qsphere-overlay-labels {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}
	.q-sphere-label {
		position: absolute;
		transform: translate(-50%, -100%);
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.65rem;
		font-weight: 700;
		text-shadow: 0 0 4px #08090f;
		white-space: nowrap;
	}

	.state-vector-amplitudes-list {
		width: 320px;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
		flex-shrink: 0;
	}
	.pane-subtitle-txt {
		font-size: 0.72rem;
		font-weight: 700;
		text-transform: uppercase;
		color: #c084fc;
		letter-spacing: 0.02em;
	}
	.sv-viewer-scroll {
		flex: 1;
		background-color: rgba(9, 11, 23, 0.3);
		border: 1px solid rgba(255, 255, 255, 0.02);
		border-radius: 6px;
		padding: 0.65rem;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.sv-detail-row {
		display: flex;
		align-items: center;
		font-size: 0.68rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.03);
		padding-bottom: 0.3rem;
	}
	.sv-detail-row:last-child { border-bottom: none; }
	.sv-state-label {
		font-family: 'JetBrains Mono', monospace;
		color: #a78bfa;
		width: 35px;
	}
	.sv-complex-num {
		font-family: 'JetBrains Mono', monospace;
		width: 90px;
		color: #94a3b8;
	}
	.sv-bar-track {
		flex: 1;
		height: 4px;
		background-color: rgba(255, 255, 255, 0.03);
		border-radius: 2px;
		overflow: hidden;
		margin-right: 0.5rem;
		max-width: 60px;
	}
	.sv-bar-fill {
		height: 100%;
		background-color: #0284c7;
	}
	.sv-val-amp {
		color: #94a3b8;
		width: 85px;
		text-align: right;
	}

	/* 2D Heatmap visualizer */
	.coupling-map-pane {
		gap: 1.5rem;
	}
	.coupling-lattice-graph {
		flex: 1;
		background-color: rgba(9, 11, 23, 0.3);
		border: 1px solid rgba(255, 255, 255, 0.02);
		border-radius: 6px;
		display: flex;
		flex-direction: column;
		padding: 0.65rem;
		box-sizing: border-box;
	}
	.lattice-workspace {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.lattice-svg {
		width: 100%;
		height: 100%;
		max-height: 300px;
	}
	.coupling-line {
		stroke: rgba(167, 139, 250, 0.15);
		stroke-width: 3;
		stroke-dasharray: 4 3;
		transition: all 0.3s ease;
	}
	.coupling-line.active {
		stroke: #c084fc;
		stroke-width: 4;
		stroke-dasharray: none;
		filter: drop-shadow(0 0 3px rgba(192, 132, 252, 0.6));
	}
	.lattice-qubit-circle {
		transition: fill 0.3s ease;
	}
	.coupling-instructions {
		width: 280px;
		font-size: 0.68rem;
		color: #64748b;
		line-height: 1.35;
		align-self: center;
	}

	/* --- Job Pipeline Status Bar --- */
	.dock-status-pipeline {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.45rem 1rem;
		background-color: rgba(13, 17, 36, 0.45);
		border: 1px solid rgba(139, 92, 246, 0.12);
		border-radius: 8px;
		font-size: 0.75rem;
	}
	.status-indicator {
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}
	.status-pulse-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
	.status-pulse-dot.SUBMITTING { background-color: #6b7280; }
	.status-pulse-dot.QUEUED { background-color: #a78bfa; animation: blink 1s infinite; }
	.status-pulse-dot.RUNNING { background-color: #06b6d4; animation: blink 1s infinite; }
	.status-pulse-dot.COMPLETED { background-color: #10b981; box-shadow: 0 0 6px #10b981; }
	.status-pulse-dot.FAILED { background-color: #ef4444; }

	.job-id-lbl {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.72rem;
		color: #64748b;
	}
	.error-strip { color: #f87171; font-size: 0.72rem; margin-left: 1rem; }

	/* --- Right Panel: Cirq Code Exporter --- */
	.right-code-sidebar {
		width: 320px;
		border-left: 1px solid rgba(139, 92, 246, 0.12);
		background-color: rgba(13, 17, 36, 0.45);
		display: flex;
		flex-direction: column;
		box-sizing: border-box;
		flex-shrink: 0;
		transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.right-code-sidebar.collapsed { width: 42px; }

	.btn-expand-sidebar {
		width: 100%;
		height: 100%;
		background: none;
		border: none;
		color: #94a3b8;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: space-between;
		padding: 1.5rem 0;
		box-sizing: border-box;
		outline: none;
	}
	.btn-expand-sidebar:hover { background-color: rgba(255, 255, 255, 0.03); }

	.code-header {
		padding: 0.5rem;
		border-bottom: 1px solid rgba(139, 92, 246, 0.1);
		background-color: rgba(9, 11, 23, 0.3);
		display: flex;
		align-items: center;
	}
	.btn-collapse-sidebar {
		background: none;
		border: none;
		color: #94a3b8;
		cursor: pointer;
		font-size: 0.75rem;
		padding: 0.25rem;
		border-radius: 4px;
	}
	.code-title-lbl {
		font-size: 0.75rem;
		font-weight: 600;
		color: #94a3b8;
		margin-left: 0.45rem;
		flex: 1;
	}
	.btn-compile-preview {
		background: none;
		border: 1px solid rgba(255,255,255,0.06);
		color: #94a3b8;
		font-size: 0.68rem;
		font-weight: 600;
		padding: 0.2rem 0.45rem;
		border-radius: 3px;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-compile-preview.active {
		background-color: rgba(167, 139, 250, 0.08);
		border-color: #a78bfa;
		color: #c084fc;
	}

	.code-editor-body {
		flex: 1;
		overflow: auto;
		display: flex;
		flex-direction: column;
		padding: 1rem;
		box-sizing: border-box;
		background-color: #05060d;
	}
	.code-utilities-row {
		display: flex;
		margin-bottom: 0.75rem;
	}
	.btn-copy-code {
		background-color: rgba(255, 255, 255, 0.03);
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: #cbd5e1;
		padding: 0.25rem 0.55rem;
		border-radius: 4px;
		font-size: 0.7rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-copy-code:hover {
		border-color: #a78bfa;
		color: #c084fc;
	}

	.code-editor-area {
		margin: 0;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		line-height: 1.45;
		white-space: pre;
		color: #e2e8f0;
	}

	/* Syntax classes */
	:global(.code-kw) { color: #f472b6; font-weight: 600; }
	:global(.code-fn) { color: #38bdf8; }
	:global(.code-str) { color: #34d399; }
	:global(.code-comment) { color: #64748b; font-style: italic; }
	:global(.code-num) { color: #fb923c; }

	/* --- Context Menu (placed gate configure) --- */
	.context-menu-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 90;
	}
	.gate-context-menu {
		position: fixed;
		background-color: #0c0e18;
		border: 1px solid rgba(139, 92, 246, 0.25);
		box-shadow: 0 10px 20px rgba(0,0,0,0.5);
		border-radius: 8px;
		padding: 0.85rem;
		z-index: 91;
		width: 200px;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.menu-title {
		font-size: 0.8rem;
		font-weight: 700;
		text-transform: uppercase;
		color: #a78bfa;
		margin: 0;
	}
	.menu-field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.menu-field label {
		font-size: 0.7rem;
		color: #94a3b8;
		font-weight: 600;
	}
	.menu-input {
		background-color: #05060d;
		border: 1px solid rgba(255, 255, 255, 0.08);
		color: #f1f5f9;
		padding: 0.3rem;
		border-radius: 4px;
		font-size: 0.75rem;
		outline: none;
	}
	.menu-input:focus { border-color: #a78bfa; }
	
	.menu-actions {
		display: flex;
		gap: 0.4rem;
	}
	.btn-menu-action {
		flex: 1;
		background-color: rgba(255, 255, 255, 0.02);
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: inherit;
		padding: 0.35rem;
		border-radius: 4px;
		font-size: 0.72rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s;
	}
	.btn-menu-action.delete {
		background-color: rgba(239, 68, 68, 0.08);
		border-color: rgba(239, 68, 68, 0.15);
		color: #ef4444;
	}
	.btn-menu-action:hover { opacity: 0.9; }

	.mt-2 { margin-top: 0.5rem; }
	.mt-3 { margin-top: 0.75rem; }
	.spinner {
		width: 13px;
		height: 13px;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		display: inline-block;
		vertical-align: middle;
	}
	@keyframes spin { to { transform: rotate(360deg); } }
</style>
