let status = {
    agent: "running",
    lastUpdate: new Date().toISOString()
};

setInterval(() => {
    let newTimeISOString = new Date().toISOString();;
    if (newDate > Date.parse(status.lastUpdate)) {
        status.lastUpdate = newTimeISOString;
    }
}, 1000);
document.body.innerHTML = JSON.stringify(status, null, 4);
