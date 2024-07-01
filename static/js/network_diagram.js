document.addEventListener('DOMContentLoaded', function () {
    fetch('/api/nodes_and_edges')
        .then(response => response.json())
        .then(data => {
            console.log('Nodes:', data.nodes);
            console.log('Edges:', data.edges);

            var cy = cytoscape({
                container: document.getElementById('cy'),
                elements: {
                    nodes: data.nodes,
                    edges: data.edges
                },
                style: [
                    {
                        selector: 'node[role="subnet"]',
                        style: {
                            'shape': 'ellipse',
                            'label': 'data(id)',
                            'width': 150,
                            'height': 40,
                            'background-color': '#D3D3D3',
                            'text-valign': 'center',
                            'color': '#fff',
                            'text-outline-width': 2,
                            'text-outline-color': '#888'
                        }
                    },
                    {
                        selector: 'node[role="Router"]',
                        style: {
                            'shape': 'rectangle',
                            'background-image': 'url(/static/images/router.png)',
                            'background-fit': 'cover',
                            'label': 'data(id)',
                            'width': 80,
                            'height': 55,
                            'text-valign': 'center',
                            'color': '#fff',
                            'text-outline-width': 2,
                            'text-outline-color': '#888'
                        }
                    },
                    {
                        selector: 'node[role="Access Switch"]',
                        style: {
                            'shape': 'rectangle',
                            'background-image': 'url(/static/images/switch.png)',
                            'background-fit': 'cover',
                            'label': 'data(id)',
                            'width': 90,
                            'height': 50,
                            'text-valign': 'center',
                            'color': '#fff',
                            'text-outline-width': 2,
                            'text-outline-color': '#888'
                        }
                    },
                    {
                        selector: 'node[role="vrf"], node[role="tenant"]',
                        style: {
                            'shape': 'roundrectangle',
                            'background-opacity': 0,  // Ensure background is transparent
                            'border-width': 2,
                            'border-color': 'data(borderColor)',  // Dynamic border color
                            'label': 'data(id)',
                            'text-valign': 'top',
                            'text-halign': 'center'
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': 3,
                            'line-color': '#ccc',
                            'target-arrow-color': '#ccc',
                            'target-arrow-shape': 'triangle',
                            'label': 'data(id)'
                        }
                    },
                    {
                        selector: '.highlighted',
                        style: {
                            'border-width': 6,
                            'border-color': 'yellow',
                            'background-color': 'yellow',
                            'line-color': 'red',
                            'target-arrow-color': 'red',
                            'transition-property': 'border-width, border-color, background-color, line-color, target-arrow-color',
                            'transition-duration': '0.5s'
                        }
                    }
                ],
                layout: {
                    name: 'cola',
                    nodeSpacing: 10,
                    edgeLengthVal: 45
                }
            });

            function highlightPath(path) {
                path.forEach(ele => {
                    console.log('Highlighting element:', ele.id());
                    cy.getElementById(ele.id()).addClass('highlighted');
                });
            }

            function clearHighlightedPath() {
                cy.elements().removeClass('highlighted');
            }

            let startNode = null;
            let endNode = null;

            cy.on('tap', 'node', function(event) {
                let node = event.target;

                // Check if the node is of type vrf or tenant and prevent selection
                if (node.data('role') === 'vrf' || node.data('role') === 'tenant') {
                    console.log('Node selection prevented for:', node.id());
                    return;
                }

                if (!startNode) {
                    startNode = node;
                    node.addClass('highlighted');
                    console.log('Start node selected:', startNode.id());
                } else if (!endNode) {
                    endNode = node;
                    node.addClass('highlighted');
                    console.log('End node selected:', endNode.id());
                }

                if (startNode && endNode) {
                    const options = {
                        root: startNode,
                        goal: endNode,
                        weight: edge => 1
                    };

                    const astar = cy.elements().aStar(options);

                    if (astar.found) {
                        console.log('Path found from ' + startNode.id() + ' to ' + endNode.id());
                        const path = astar.path;
                        console.log('Calculated path:', path.map(ele => ele.id()));
                        highlightPath(path);
                    } else {
                        console.log('No path found from ' + startNode.id() + ' to ' + endNode.id());
                    }

                    // Reset start and end nodes for next selection
                    startNode = null;
                    endNode = null;
                }
            });

            document.getElementById('clearPathBtn').addEventListener('click', function () {
                clearHighlightedPath();
            });

            document.getElementById('exportPNGBtn').addEventListener('click', function () {
                var png = cy.png();
                var link = document.createElement('a');
                link.href = png;
                link.download = 'network_diagram.png';
                link.click();
            });

            document.getElementById('exportSVGBtn').addEventListener('click', function () {
                var svg = cy.svg();
                var link = document.createElement('a');
                link.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
                link.download = 'network_diagram.svg';
                link.click();
            });
        });
});
