import com.sun.tools.attach.VirtualMachine;

/** Bounded CPU load inside the actual TeaStore JVM, with an explicit stop action. */
public class FaultAgent {
    private static volatile Thread worker;
    private static volatile double sink;

    public static synchronized void agentmain(String arguments) {
        if (worker != null) worker.interrupt();
        if (arguments.equals("stop")) return;
        int seconds = Integer.parseInt(arguments);
        if (seconds < 1 || seconds > 180) throw new IllegalArgumentException("Duration must be 1..180s");
        worker = new Thread(() -> {
            long deadline = System.nanoTime() + seconds * 1_000_000_000L;
            double value = 0.123;
            while (!Thread.currentThread().isInterrupted() && System.nanoTime() < deadline) {
                for (int i = 0; i < 10000; i++) value = Math.sin(value + i);
                sink = value;
            }
        }, "ai-chaos-bounded-cpu");
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
