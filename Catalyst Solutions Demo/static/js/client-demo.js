/* Fictional client-facing records; kept separate from employee demo screens. */
window.CLIENT_DEMO = {
  project: {
    description: 'Complete kitchen renovation with shaker cabinets, quartz countertops, tile backsplash, updated lighting, and new flooring.',
    address: '1234 Riverstone Blvd, Houston, TX 77008'
  },
  estimates: [
    {estimate_number:'EST-RIVERSTONE', title:'Kitchen Remodel Estimate', status:'Approved', date:'2026-10-12', line_items:[
      {description:'Cabinets, countertops, flooring, and fixtures',quantity:1,unit_cost:21000},
      {description:'Demolition and installation labor',quantity:1,unit_cost:15000},
      {description:'Equipment rental',quantity:1,unit_cost:2500},
      {description:'Licensed electrical and plumbing work',quantity:1,unit_cost:7500},
      {description:'Permits and inspections',quantity:1,unit_cost:1000},
      {description:'Site protection and miscellaneous supplies',quantity:1,unit_cost:1500}
    ]},
    {estimate_number:'EST-CHANGE-01',title:'Pantry Storage Upgrade',status:'Pending Review',date:'2026-11-10',line_items:[
      {description:'Pull-out pantry organizers',quantity:3,unit_cost:450},
      {description:'Custom shelving installation',quantity:10,unit_cost:100}
    ]},
    {estimate_number:'EST-CHANGE-02',title:'Premium Appliance Package',status:'Rejected',date:'2026-10-25',line_items:[
      {description:'Premium appliance upgrade allowance',quantity:1,unit_cost:5800},
      {description:'Appliance installation',quantity:1,unit_cost:600}
    ]}
  ],
  invoices: [
    {id:1025,number:'1025',project_id:1,date:'2026-09-15',due:'2026-09-29',status:'Paid',kind:'client',lines:[{description:'Initial project deposit',quantity:1,rate:10000}]},
    {id:1032,number:'1032',project_id:1,date:'2026-10-01',due:'2026-10-15',status:'Paid',kind:'client',lines:[{description:'Demolition and site preparation',quantity:1,rate:4500},{description:'Electrical rough-in',quantity:1,rate:1750}]},
    {id:1048,number:'1048',project_id:1,date:'2026-11-10',due:'2026-11-24',status:'Unpaid',kind:'client',lines:[{description:'Quartz countertop fabrication deposit',quantity:1,rate:3000},{description:'Backsplash tile materials',quantity:1,rate:1200}]}
  ],
  activity: [
    {date:'2026-11-12',text:'Cabinet installation is in progress. Countertop measurements follow cabinet completion.'},
    {date:'2026-11-10',text:'Pantry storage upgrade estimate submitted for review.'},
    {date:'2026-11-10',text:'Invoice #1048 issued for countertops and backsplash materials.'},
    {date:'2026-10-12',text:'Kitchen remodel estimate approved for $48,500.'},
    {date:'2026-09-15',text:'Initial project deposit received. Thank you!'}
  ]
};
