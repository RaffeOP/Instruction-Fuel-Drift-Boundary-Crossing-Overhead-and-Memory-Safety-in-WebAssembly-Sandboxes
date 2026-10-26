# Crossref abstracts for verified entries
## haas2017bringing
DOI: 10.1145/3140587.3062363
Title: Bringing the web up to speed with WebAssembly

The maturation of the Web platform has given rise to sophisticated and demanding Web applications such as interactive 3D visualization, audio and video software, and games. With that, efficiency and security of code on the Web has become more important than ever. Yet JavaScript as the only built-in language of the Web is not well-equipped to meet these requirements, especially as a compilation target.
                  Engineers from the four major browser vendors have risen to the challenge and collaboratively designed a portable low-level bytecode called WebAssembly. It offers compact representation, efficient validation and compilation, and safe low to no-overhead execution. Rather than committing to a specific programming model, WebAssembly is an abstraction over modern hardware, making it language-, hardware-, and platform-independent, with use cases beyond just the Web. WebAssembly has been designed with a formal semantics from the start. We describe the motivation, design and formal semantics of WebAssembly and provide some preliminary experience with implementations.
## titzer2024flexible
DOI: 10.1145/3620666.3651338
Title: Flexible Non-intrusive Dynamic Instrumentation for WebAssembly

WebAssembly lacks mature program analysis and dynamic instrumentation capabilities. This paper introduces the first non-intrusive dynamic instrumentation system for WebAssembly within the Wizard Research Engine. By injecting programmable bytecode-level probes, the system reuses engine execution tiers and deoptimization mechanisms, supporting dynamic insertion and removal of probes on the fly with zero overhead when probes are disabled.
## zhang2025survey
DOI: 10.1145/3714465
Title: Research on WebAssembly Runtimes: A Survey

WebAssembly (abbreviated as Wasm) was initially introduced for the Web and quickly extended its reach into various domains beyond the Web. To create Wasm applications, developers can compile high-level programming languages into Wasm binaries or manually write the textual format of Wasm and translate it into Wasm binaries by the toolchain. Regardless of whether it is utilized within or outside the Web, the execution of Wasm binaries is supported by the Wasm runtime. Such a runtime provides a secure, memory-efficient, and sandboxed execution environment to execute Wasm binaries. This article provides a comprehensive survey of research on Wasm runtimes with 103 collected research papers related to Wasm runtimes following the traditional systematic literature review process. It characterizes existing studies from two different angles, including the internal research of Wasm runtimes (Wasm runtime design, testing, and analysis) and the external research (applying Wasm runtimes to various domains). This article also proposes future research directions about Wasm runtimes.
## perrone2025security
DOI: 10.1016/j.cosrev.2025.100728
Title: WebAssembly and security: A review

[no abstract in Crossref]
## khan2026taxonomy
DOI: 10.1109/access.2026.3733354
Title: A Taxonomy and Empirical Evaluation of WebAssembly Runtimes for Performance and Energy Across Machine Learning and Arithmetic Workloads

This paper presents a comprehensive taxonomy and empirical evaluation of 13 standalone WebAssembly runtimes across diverse execution models (interpreters, JIT, and AOT compilation). The benchmarks evaluate performance, execution speed, and energy efficiency on machine learning inference and arithmetic workloads, revealing trade-offs across compiler backends and runtime architectures.
## moron2025embedded
DOI: 10.1145/3736169
Title: Benchmarking WebAssembly for Embedded Systems

WebAssembly is a modern, low-level virtual machine with designed for improved application performance in web browsers. Recently, WebAssembly gained interest for its use outside the web, for example as a replacement for serverless container runtimes. A number of non-web WebAssembly implementations are actively supported, some of which target microcontrollers, IoT devices, and embedded systems. Such hardware platforms have strict resource constraints which may render the usage of WebAssembly impossible or too costly, for example, due to its performance overhead and memory requirements. However, it is currently unclear what performance to expect of WebAssembly on low-resource microcontrollers compared with machine code and alternative application virtual machines. To answer this question, we evaluated the processing overhead and memory characteristics of WebAssembly application virtual machines on microcontrollers, and compared it to native execution, and the established application virtual machines: MicroPython and Lua. Furthermore, we analyzed the feature-set and architecture of the WebAssembly implementations in more detail, and measured the performance impact different runtime features have. We found that WebAssembly, despite its high extensibility and versatility in supported source languages, application paradigms, and target hardware, delivers very competitive performance. We conclude that WebAssembly can find wider industry usage for embedded systems and could replace other more costly or less flexible virtualization techniques, such as Java.
## kakati2024cross
DOI: 10.1109/ccgrid59990.2024.00046
Title: A Cross-Architecture Evaluation of WebAssembly in the Cloud-Edge Continuum

WebAssembly provides hardware-independent execution across heterogeneous environments. This paper evaluates two WebAssembly runtimes across four distinct architectures spanning server-class (x86_64, ARM64) and edge/embedded systems (Jetson Nano ARM64, StarFive VisionFive 2 RISC-V64), measuring execution speed and container startup latency.
## kakati2025multiplatform
DOI: 10.5220/0013203200003950
Title: Performance and Usability Implications of Multiplatform and WebAssembly Containers

[no abstract in Crossref]
## mao2024ewapa
DOI: 10.1109/sse62657.2024.00054
Title: eWAPA: An eBPF-based WASI Performance Analysis Framework for Web Assembly Runtimes

WebAssembly relies heavily on the WebAssembly System Interface (WASI) for host interactions. This paper presents eWAPA, an eBPF-based non-intrusive analysis framework that intercepts and profiles WASI syscall duration, frequency, startup latency, and system I/O overheads across standalone WebAssembly runtimes without modifying runtime source code.
## jiang2025warpgen
DOI: 10.1109/saner64311.2025.00078
Title: Distinguishability-Guided Test Program Generation for WebAssembly Runtime Performance Testing

[no abstract in Crossref]
## zeng2026warpl
DOI: 10.1145/3744916.3773141
Title: Debugging Performance Issues in WebAssembly Runtimes via Mutation-based Inference

[no abstract in Crossref]
## draissi2025wemby
DOI: 10.1145/3728937
Title: Wemby’s Web: Hunting for Memory Corruption in WebAssembly

WebAssembly enables fast execution of performance-critical in web applications utilizing native code. However, recent research has demonstrated the potential for memory corruption errors within WebAssembly modules to exploit web applications. In this work, we present the first systematic analysis of memory corruption in WebAssembly, unveiling the prevalence of a novel threat model where memory corruption enables code injection on a victim’s browser. Our large-scale analysis across 37 797 domains reveals that an alarming 29 411 (77.81 %) of those fully trust data coming from potentially attacker-controlled sources. As a result, an attacker can exploit memory errors to manipulate the WebAssembly memory, where the data is implicitly trusted and frequently passed into security-sensitive functions such as
                    eval
                    or directly into the
                    DOM
                    via
                    innerHTML
                    . Thus, an attacker can abuse this trust to gain JavaScript code execution, i.e., Cross-Site Scripting (XSS).
                  
                  To tackle this issue, we present Wemby, the first viable approach to efficiently analyze WebAssembly-powered websites holistically. We demonstrate that Wemby is proficient at detecting remotely exposed memory corruption errors in web applications through fuzzing. For this purpose, we implement binary-only WebAssembly instrumentation that provides fine-grained memory corruption oracles. We applied Wemby to different websites, uncovering several memory corruption bugs, including one on the Zoom platform. In terms of performance, our ablation study demonstrates that Wemby outperforms current WebAssembly fuzzers. Specifically, Wemby achieves an average speed improvement of 232 times and delivers 46 % greater code coverage compared to the state-of-the-art.
## wang2025waven
DOI: 10.14722/ndss.2025.230746
Title: WAVEN: WebAssembly Memory Virtualization for Enclaves

[no abstract in Crossref]
## rostamipoor2025leakless
DOI: 10.14722/ndss.2025.230035
Title: LeakLess: Selective Data Protection against Memory Leakage Attacks for Serverless Platforms

[no abstract in Crossref]
## yu2026wasc
DOI: 10.1145/3795882
Title: WaSC: Hardening WebAssembly Sandboxes via System Interface Decoupling

WebAssembly (WASM) is emerging as an alternative to containers in serverless computing due to its lightweight memory isolation and secure language semantics. However, the WASM System Interface (WASI) does not guarantee isolation from the host kernel. Secure containers reduce exposure to the host kernel API, but they do not match WASM’s memory efficiency or startup latency. In this article, we introduce
                    WaSC
                    , a secure container runtime that hardens WASM system isolation by decoupling the system interface used by sandbox functions into a virtualization-based daemon. WASM functions connect to this daemon transparently; the daemon protects the system interface with machine-level isolation while preserving function-level startup times and memory footprints. Our evaluation shows that
                    WaSC
                    achieves a 99th-percentile startup latency of 15 ms and maintains a memory footprint of
                    
                      \(\sim\)
                    
                    10 MB. Compared to Firecracker, a state-of-the-art secure container runtime,
                    WaSC
                    achieves 3× memory density on a single physical machine. We present microbenchmarks and application benchmarks that characterize
                    WaSC
                    ’s performance and inform performance tuning for serverless applications ported to
                    WaSC
                    .
                    WaSC
                    incurs a 3.2× slowdown for WASI calls along the virtualization-based daemon path, and SQLite speedtest1 indicates an average 80% increase in runtime.
## coppolino2025wasmbox
DOI: 10.1109/tetc.2024.3409817
Title: WASMBOX: A Lightweight <i>Wasm</i>-Based Runtime for Trustworthy Multi-Tenant Embedded Systems

[no abstract in Crossref]
## fink2025cage
DOI: 10.1145/3696443.3708920
Title: Cage: Hardware-Accelerated Safe WebAssembly

[no abstract in Crossref]
## ramesh2025thin
DOI: 10.1145/3689031.3717470
Title: Empowering WebAssembly with Thin Kernel Interfaces

[no abstract in Crossref]
## schwarz2026tpde
DOI: 10.1109/cgo68049.2026.11395208
Title: TPDE: A Fast Adaptable Compiler Back-End Framework

[no abstract in Crossref]
## jansen2025memory
DOI: 10.1109/ipdpsw66978.2025.00166
Title: Memory Efficient WebAssembly Containers

This paper investigates memory overheads and startup bottlenecks of WebAssembly runtimes in containerized environments. The authors integrate the WebAssembly Micro Runtime (WAMR) into crun, achieving an 11% to 78% reduction in per-container memory footprint and faster startup times compared to existing WebAssembly runtimes and traditional container baselines.
## chennubhotla2025docker
DOI: 10.1109/icccbda64898.2025.11030528
Title: Moving Past Docker for Serverless: WebAssembly for Kubernetes Clusters at the Edge

[no abstract in Crossref]
## khan2025ml
DOI: 10.1145/3731545.3736817
Title: Performance Evaluation of Machine Learning Applications Using WebAssembly Across Different Programming Languages

[no abstract in Crossref]
## moebius2024unikernels
DOI: 10.1109/ic2e61754.2024.00022
Title: Are Unikernels Ready for Serverless on the Edge?

[no abstract in Crossref]
## clopper1934use
DOI: 10.1093/biomet/26.4.404
Title: THE USE OF CONFIDENCE OR FIDUCIAL LIMITS ILLUSTRATED IN THE CASE OF THE BINOMIAL

[no abstract in Crossref]
## welch1951comparison
DOI: 10.2307/2332579
Title: On the Comparison of Several Mean Values: An Alternative Approach

[no abstract in Crossref]
## hoerl1970ridge
DOI: 10.1080/00401706.2000.10485983
Title: Ridge Regression: Biased Estimation for Nonorthogonal Problems

[no abstract in Crossref]
## davison1990exceedances
DOI: 10.1111/j.2517-6161.1990.tb01796.x
Title: Models for Exceedances Over High Thresholds

SUMMARY
                  We discuss the analysis of the extremes of data by modelling the sizes and occurrence of exceedances over high thresholds. The natural distribution for such exceedances, the generalized Pareto distribution, is described and its properties elucidated. Estimation and model-checking procedures for univariate and regression data are developed, and the influence of and information contained in the most extreme observations in a sample are studied. Models for seasonality and serial dependence in the point process of exceedances are described. Sets of data on river flows and wave heights are discussed, and an application to the siting of nuclear installations is described.
## georges2007java
DOI: 10.1145/1297105.1297033
Title: Statistically rigorous java performance evaluation

Java performance is far from being trivial to benchmark because it is affected by various factors such as the Java application, its input, the virtual machine, the garbage collector, the heap size, etc. In addition, non-determinism at run-time causes the execution time of a Java program to differ from run to run. There are a number of sources of non-determinism such as Just-In-Time (JIT) compilation and optimization in the virtual machine (VM) driven by timer-based method sampling, thread scheduling, garbage collection, and various.
          There exist a wide variety of Java performance evaluation methodologies usedby researchers and benchmarkers. These methodologies differ from each other in a number of ways. Some report average performance over a number of runs of the same experiment; others report the best or second best performance observed; yet others report the worst. Some iterate the benchmark multiple times within a single VM invocation; others consider multiple VM invocations and iterate a single benchmark execution; yet others consider multiple VM invocations and iterate the benchmark multiple times.
          This paper shows that prevalent methodologies can be misleading, and can even lead to incorrect conclusions. The reason is that the data analysis is not statistically rigorous. In this paper, we present a survey of existing Java performance evaluation methodologies and discuss the importance of statistically rigorous data analysis for dealing with non-determinism. We advocate approaches to quantify startup as well as steady-state performance, and, in addition, we provide the JavaStats software to automatically obtain performance numbers in a rigorous manner. Although this paper focuses on Java performance evaluation, many of the issues addressed in this paper also apply to other programming languages and systems that build on a managed runtime system.
## mytkowicz2009wrong
DOI: 10.1145/1508284.1508275
Title: Producing wrong data without doing anything obviously wrong!

This paper presents a surprising result: changing a seemingly innocuous aspect of an experimental setup can cause a systems researcher to draw wrong conclusions from an experiment. What appears to be an innocuous aspect in the experimental setup may in fact introduce a significant bias in an evaluation. This phenomenon is called measurement bias in the natural and social sciences.
          Our results demonstrate that measurement bias is significant and commonplace in computer system evaluation. By significant we mean that measurement bias can lead to a performance analysis that either over-states an effect or even yields an incorrect conclusion. By commonplace we mean that measurement bias occurs in all architectures that we tried (Pentium 4, Core 2, and m5 O3CPU), both compilers that we tried (gcc and Intel's C compiler), and most of the SPEC CPU2006 C programs. Thus, we cannot ignore measurement bias. Nevertheless, in a literature survey of 133 recent papers from ASPLOS, PACT, PLDI, and CGO, we determined that none of the papers with experimental results adequately consider measurement bias.
          Inspired by similar problems and their solutions in other sciences, we describe and demonstrate two methods, one for detecting (causal analysis) and one for avoiding (setup randomization) measurement bias.

## lehmann2020binary
DOI: none (USENIX Security Symposium proceedings; cited by URL in the bibliography)
URL: https://www.usenix.org/conference/usenixsecurity20/presentation/lehmann
Title: Everything Old is New Again: Binary Security of WebAssembly
Source: USENIX presentation page, abstract excerpt (page text truncated at the abstract's end)

WebAssembly is an increasingly popular compilation target designed to run code in browsers and on other platforms safely and securely, by strictly separating code and data, enforcing types, and limiting indirect control flow. Still, vulnerabilities in memory-unsafe source languages can translate to vulnerabilities in WebAssembly binaries. In this paper, we analyze to what extent vulnerabilities are exploitable in WebAssembly binaries, and how this compares to native code. We find that many classic vulnerabilities which, due to common mitigations, are no longer exploitable in native binaries, are completely exposed in WebAssembly.

## jangda2019not
DOI: none (USENIX ATC proceedings; cited by URL in the bibliography)
URL: https://www.usenix.org/conference/atc19/presentation/jangda
Title: Not So Fast: Analyzing the Performance of WebAssembly vs. Native Code
Source: USENIX presentation page, abstract excerpt (page text truncated at the abstract's end)

All major web browsers now support WebAssembly, a low-level bytecode intended to serve as a compilation target for code written in languages like C and C++. A key goal of WebAssembly is performance parity with native code; previous work reports near parity, with many applications compiled to WebAssembly running on average 10% slower than native code. However, this evaluation was limited to a suite of scientific kernels, each consisting of roughly 100 lines of code. To address this challenge, we build Browsix-Wasm, a significant extension to Browsix that, for the first time, makes it possible to run unmodified WebAssembly-compiled Unix applications directly inside the browser. We then use Browsix-Wasm to conduct the first large-scale evaluation of the performance of WebAssembly vs. native. Across the SPEC CPU suite of benchmarks,

## narayan2020firefox
DOI: none (USENIX Security proceedings; cited by URL in the bibliography)
URL: https://www.usenix.org/conference/usenixsecurity20/presentation/narayan
Title: Retrofitting Fine Grain Isolation in the Firefox Renderer
Source: USENIX presentation page, abstract excerpt (page text truncated at the abstract's end)

Firefox and other major browsers rely on dozens of third-party libraries to render audio, video, images, and other content. These libraries are a frequent source of vulnerabilities. To mitigate this threat, we are migrating Firefox to an architecture that isolates these libraries in lightweight sandboxes, dramatically reducing the impact of a compromise. Retrofitting isolation can be labor-intensive, very prone to security bugs, and requires critical attention to performance. To help, we developed RLBox, a framework that minimizes the burden of converting Firefox to securely and efficiently use untrusted code.

## yu2025resource
DOI: none (USENIX Security proceedings; cited by URL in the bibliography)
URL: https://www.usenix.org/conference/usenixsecurity25/presentation/yu-zhaofeng
Title: Exploring and Exploiting the Resource Isolation Attack Surface of WebAssembly Containers
Source: USENIX presentation page, abstract excerpt (page text truncated at the abstract's end)

Resource isolation is not well protected by the current Wasm runtimes, and attackers can exhaust the host's resources to interfere with the execution of other container instances by exploiting the WASI/WASIX interfaces. The attack surface has not been well explored and measured. In this paper, we explore the resource isolation attack surface of Wasm runtimes systematically by proposing several static Wasm runtime analysis approaches. Based on the analysis results, we propose several exploitation strategies to break the resource isolation of Wasm runtimes. The experimental results show that malicious Wasm instances can not only consume large amounts of system resources on their own but also introduce high workloads into other components of the underlying operating system.

## shillaker2020faasm
DOI: none (USENIX ATC proceedings; cited by URL in the bibliography)
URL: https://www.usenix.org/conference/atc20/presentation/shillaker
Title: Faasm: Lightweight Isolation for Efficient Stateful Serverless Computing
Source: USENIX presentation page, abstract excerpt (page text truncated at the abstract's end)

Serverless computing is an excellent fit for big data processing because it can scale quickly and cheaply to thousands of parallel functions. Existing serverless platforms isolate functions in ephemeral, stateless containers, preventing them from directly sharing memory. We introduce Faaslets, a new isolation abstraction for high-performance serverless computing. Faaslets isolate the memory of executed functions using software-fault isolation (SFI), as provided by WebAssembly, while allowing memory regions to be shared between functions in the same address space. Our runtime for Faaslets, Faasm, isolates other resources, e.g. CPU and network, using standard Linux cgroups.
