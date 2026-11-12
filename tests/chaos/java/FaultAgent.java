import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

/**
 * Bounded CPU load or heap/GC pressure inside the actual TeaStore JVM, with an explicit stop action.
 *
 * Memory mode is a gradual leak: it pins at most LEAK_STEP_BYTES per tick and stops growing at
 * 86% of the max heap or when the container working set (cgroup memory.current minus
 * inactive_file, as Kubernetes computes it) reaches CGROUP_CEILING of memory.max, so the
 * fault produces heap/GC pressure without an instant kernel OOM kill of the container.
 */
public class FaultAgent {
    private static volatile Thread worker;
    private static volatile double sink;
    private static volatile List<byte[]> pinned;
    private static final long LEAK_STEP_BYTES = 6L * 1024 * 1024;   // ~6.7 MiB/s at a 0.9s tick
    private static final double CGROUP_CEILING = 0.88;
    private static final Path CGROUP = Paths.get("/sys/fs/cgroup");

    /** True when the container working set stays below CGROUP_CEILING of its limit (or no limit is readable). */
    static boolean containerHasHeadroom() {
        try {
            String max = new String(Files.readAllBytes(CGROUP.resolve("memory.max"))).trim();
            if (max.equals("max")) return true;
            long limit = Long.parseLong(max);
            long current = Long.parseLong(new String(Files.readAllBytes(CGROUP.resolve("memory.current"))).trim());
            long inactiveFile = 0;
            for (String line : Files.readAllLines(CGROUP.resolve("memory.stat"))) {
                if (line.startsWith("inactive_file ")) inactiveFile = Long.parseLong(line.substring(14).trim());
            }
            return (current - inactiveFile) + 512 * 1024 < CGROUP_CEILING * limit;
        } catch (Exception unreadable) {
            return false;   // no cgroup v2 accounting: never pin beyond what is already held
        }
    }

    private static synchronized void releaseMemory() {
        if (pinned != null) {
            pinned.clear();
            pinned = null;
            System.gc();
        }
    }

    public static synchronized void agentmain(String arguments) {
        if (worker != null) {
            worker.interrupt();
            try {
                worker.join(2000);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }
        releaseMemory();
        if (arguments.equals("stop")) return;
        boolean memoryMode = arguments.startsWith("memory:");
        int seconds = Integer.parseInt(memoryMode ? arguments.substring(7) : arguments);
        if (seconds < 1 || seconds > 180) throw new IllegalArgumentException("Duration must be 1..180s");
        if (memoryMode) {
            worker = new Thread(() -> {
                long deadline = System.nanoTime() + seconds * 1_000_000_000L;
                List<byte[]> holder = new ArrayList<>();
                pinned = holder;
                try {
                    Runtime rt = Runtime.getRuntime();
                    long maxHeap = rt.maxMemory();
                    long targetUsed = (long) (maxHeap * 0.86);
                    while (!Thread.currentThread().isInterrupted() && System.nanoTime() < deadline) {
                        long used = rt.totalMemory() - rt.freeMemory();
                        long pinnedThisTick = 0;
                        while (used < targetUsed && maxHeap - used > 20L * 1024 * 1024
                                && pinnedThisTick < LEAK_STEP_BYTES && containerHasHeadroom()) {
                            holder.add(new byte[512 * 1024]);
                            pinnedThisTick += 512 * 1024;
                            used = rt.totalMemory() - rt.freeMemory();
                        }
                        byte[][] churn = new byte[8][256 * 1024];
                        sink = churn[0].length;
                        System.gc();
                        Thread.sleep(900);
                    }
                } catch (InterruptedException | OutOfMemoryError ignored) {
                } finally {
                    releaseMemory();
                }
            }, "ai-chaos-bounded-memory");
        } else {
            worker = new Thread(() -> {
                long deadline = System.nanoTime() + seconds * 1_000_000_000L;
                double value = 0.123;
                while (!Thread.currentThread().isInterrupted() && System.nanoTime() < deadline) {
                    for (int i = 0; i < 10000; i++) value = Math.sin(value + i);
                    sink = value;
                }
            }, "ai-chaos-bounded-cpu");
        }
        worker.setDaemon(true);
        worker.start();
    }

    public static void main(String[] args) throws Exception {
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            vm.loadAgent(args[1], args[2]);
        } finally {
            vm.detach();
        }
    }
}
