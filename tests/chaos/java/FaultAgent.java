import com.sun.tools.attach.VirtualMachine;
import java.util.ArrayList;
import java.util.List;

/** Bounded CPU load or heap/GC pressure inside the actual TeaStore JVM, with an explicit stop action. */
public class FaultAgent {
    private static volatile Thread worker;
    private static volatile double sink;
    private static volatile List<byte[]> pinned;

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
                        while (used < targetUsed && maxHeap - used > 20L * 1024 * 1024) {
                            holder.add(new byte[512 * 1024]);
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
