function drawProjectChart(target, points) {
    const ledger = named('dl',undefined,'receipt-roll');
    points.slice(0,10).forEach(({label,value})=> {
        const item = named('div');
        item.append(named('dt',label),named('dd',value));
        ledger.append(item);
    });
    target.append(ledger);
}
