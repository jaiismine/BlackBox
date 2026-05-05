class MockUART:
    """
    Mock UART class for MicroPython ESP32 simulation in Wokwi.
    Redirects UART2 AT commands to the Wokwi Serial Terminal for testing GSM functionality.
    """
    def __init__(self, uart_id, tx=None, rx=None, baudrate=115200, bits=8, parity=None, stop=1, **kwargs):
        self.uart_id = uart_id
        self.tx = tx
        self.rx = rx
        self.baudrate = baudrate
        self.bits = bits
        self.parity = parity
        self.stop = stop
        print(f"MockUART initialized for UART{self.uart_id} (TX:{tx}, RX:{rx}, baudrate:{baudrate})")

    def write(self, data):
        """
        Write data to UART. For UART2, redirect AT commands to serial terminal.
        """
        if isinstance(data, bytes):
            data_str = data.decode('utf-8', errors='ignore')
        else:
            data_str = str(data)

        if self.uart_id == 2:
            # Redirect UART2 writes (AT commands) to serial terminal
            print(f"GSM AT Command: {data_str.strip()}")
        else:
            # For other UARTs, just print normally
            print(f"UART{self.uart_id} TX: {data_str.strip()}")

    def read(self, n=1):
        """
        Mock read - returns empty bytes since no physical GSM module.
        """
        return b''

    def readline(self):
        """
        Mock readline - returns empty bytes.
        """
        return b''

    def any(self):
        """
        Check if data is available - always False in mock.
        """
        return 0

    def deinit(self):
        """
        Deinitialize the UART.
        """
        print(f"MockUART{self.uart_id} deinitialized")

    # Add other UART methods if needed
    def init(self, baudrate=None, bits=None, parity=None, stop=None, **kwargs):
        if baudrate:
            self.baudrate = baudrate
        if bits:
            self.bits = bits
        if parity:
            self.parity = parity
        if stop:
            self.stop = stop
        print(f"MockUART{self.uart_id} re-initialized with baudrate:{self.baudrate}")